// SPDX-License-Identifier: GPL-2.0-or-later
/* -------------------------------------------------------------------------
 * Copyright (C) 2014-2015, Intel Corporation
 *
 * Derived from:
 *  gslX68X.c
 *  Copyright (C) 2010-2015, Shanghai Sileadinc Co.Ltd
 *
 * -------------------------------------------------------------------------
 */

#include <linux/i2c.h>
#include <linux/of.h>
#include <linux/module.h>
#include <linux/acpi.h>
#include <linux/interrupt.h>
#include <linux/gpio/consumer.h>
#include <linux/delay.h>
#include <linux/firmware.h>
#include <linux/input.h>
#include <linux/input/mt.h>
#include <linux/input/touchscreen.h>
#include <linux/pm.h>
#include <linux/pm_runtime.h>
#include <linux/irq.h>
#include <linux/regulator/consumer.h>

#include <linux/unaligned.h>

#define SILEAD_TS_NAME		"silead_ts"

#define SILEAD_REG_RESET	0xE0
#define SILEAD_REG_DATA		0x80
#define SILEAD_REG_TOUCH_NR	0x80
#define SILEAD_REG_POWER	0xBC
#define SILEAD_REG_CLOCK	0xE4
#define SILEAD_REG_STATUS	0xB0
#define SILEAD_REG_ID		0xFC
#define SILEAD_REG_MEM_CHECK	0xB0

#define SILEAD_STATUS_OK	0x5A5A5A5A
#define SILEAD_TS_DATA_LEN	44
#define SILEAD_CLOCK		0x04

#define SILEAD_CMD_RESET	0x88
#define SILEAD_CMD_START	0x00

#define SILEAD_POINT_DATA_LEN	0x04
#define SILEAD_POINT_Y_OFF      0x00
#define SILEAD_POINT_Y_MSB_OFF	0x01
#define SILEAD_POINT_X_OFF	0x02
#define SILEAD_POINT_X_MSB_OFF	0x03
#define SILEAD_EXTRA_DATA_MASK	0xF0

#define SILEAD_CMD_SLEEP_MIN	10000
#define SILEAD_CMD_SLEEP_MAX	20000
#define SILEAD_POWER_SLEEP	20
#define SILEAD_STARTUP_SLEEP	30

#define SILEAD_MAX_FINGERS	10

enum silead_ts_power {
	SILEAD_POWER_ON  = 1,
	SILEAD_POWER_OFF = 0
};

struct silead_ts_data {
	struct i2c_client *client;
	struct gpio_desc *gpio_power;
	struct input_dev *input;
	struct input_dev *pen_input;
	struct regulator_bulk_data regulators[2];
	unsigned int num_regulators;
	bool pf1007l;
	char fw_name[64];
	struct touchscreen_properties prop;
	u32 chip_id;
	struct input_mt_pos pos[SILEAD_MAX_FINGERS];
	int slots[SILEAD_MAX_FINGERS];
	int id[SILEAD_MAX_FINGERS];
	u32 efi_fw_min_max[4];
	bool efi_fw_min_max_set;
	bool pen_supported;
	bool pen_down;
	u32 pen_x_res;
	u32 pen_y_res;
	int pen_up_count;
};

struct silead_fw_data {
	u32 offset;
	u32 val;
};

static void silead_apply_efi_fw_min_max(struct silead_ts_data *data)
{
	struct input_absinfo *absinfo_x = &data->input->absinfo[ABS_MT_POSITION_X];
	struct input_absinfo *absinfo_y = &data->input->absinfo[ABS_MT_POSITION_Y];

	if (!data->efi_fw_min_max_set)
		return;

	absinfo_x->minimum = data->efi_fw_min_max[0];
	absinfo_x->maximum = data->efi_fw_min_max[1];
	absinfo_y->minimum = data->efi_fw_min_max[2];
	absinfo_y->maximum = data->efi_fw_min_max[3];

	if (data->prop.invert_x) {
		absinfo_x->maximum -= absinfo_x->minimum;
		absinfo_x->minimum = 0;
	}

	if (data->prop.invert_y) {
		absinfo_y->maximum -= absinfo_y->minimum;
		absinfo_y->minimum = 0;
	}

	if (data->prop.swap_x_y) {
		swap(absinfo_x->minimum, absinfo_y->minimum);
		swap(absinfo_x->maximum, absinfo_y->maximum);
	}
}

static int silead_ts_request_input_dev(struct silead_ts_data *data)
{
	struct device *dev = &data->client->dev;
	int error;

	data->input = devm_input_allocate_device(dev);
	if (!data->input) {
		dev_err(dev,
			"Failed to allocate input device\n");
		return -ENOMEM;
	}

	input_set_abs_params(data->input, ABS_MT_POSITION_X, 0, 4095, 0, 0);
	input_set_abs_params(data->input, ABS_MT_POSITION_Y, 0, 4095, 0, 0);
	touchscreen_parse_properties(data->input, true, &data->prop);
	silead_apply_efi_fw_min_max(data);

	input_mt_init_slots(data->input, SILEAD_MAX_FINGERS,
			    INPUT_MT_DIRECT | INPUT_MT_DROP_UNUSED |
			    INPUT_MT_TRACK);

	if (device_property_read_bool(dev, "silead,home-button"))
		input_set_capability(data->input, EV_KEY, KEY_LEFTMETA);

	data->input->name = SILEAD_TS_NAME;
	data->input->phys = "input/ts";
	data->input->id.bustype = BUS_I2C;

	error = input_register_device(data->input);
	if (error) {
		dev_err(dev, "Failed to register input device: %d\n", error);
			return error;
	}

	return 0;
}

static int silead_ts_request_pen_input_dev(struct silead_ts_data *data)
{
	struct device *dev = &data->client->dev;
	int error;

	if (!data->pen_supported)
		return 0;

	data->pen_input = devm_input_allocate_device(dev);
	if (!data->pen_input)
		return -ENOMEM;

	input_set_abs_params(data->pen_input, ABS_X, 0, 4095, 0, 0);
	input_set_abs_params(data->pen_input, ABS_Y, 0, 4095, 0, 0);
	input_set_capability(data->pen_input, EV_KEY, BTN_TOUCH);
	input_set_capability(data->pen_input, EV_KEY, BTN_TOOL_PEN);
	set_bit(INPUT_PROP_DIRECT, data->pen_input->propbit);
	touchscreen_parse_properties(data->pen_input, false, &data->prop);
	input_abs_set_res(data->pen_input, ABS_X, data->pen_x_res);
	input_abs_set_res(data->pen_input, ABS_Y, data->pen_y_res);

	data->pen_input->name = SILEAD_TS_NAME " pen";
	data->pen_input->phys = "input/pen";
	data->input->id.bustype = BUS_I2C;

	error = input_register_device(data->pen_input);
	if (error) {
		dev_err(dev, "Failed to register pen input device: %d\n", error);
		return error;
	}

	return 0;
}

static void silead_ts_set_power(struct i2c_client *client,
				enum silead_ts_power state)
{
	struct silead_ts_data *data = i2c_get_clientdata(client);

	if (data->gpio_power) {
		gpiod_set_value_cansleep(data->gpio_power, state);
		if (data->pf1007l)
			msleep(state == SILEAD_POWER_ON ? 35 : 55);
		else
			msleep(SILEAD_POWER_SLEEP);
	}
}

static bool silead_ts_handle_pen_data(struct silead_ts_data *data, u8 *buf)
{
	u8 *coord = buf + SILEAD_POINT_DATA_LEN;
	struct input_mt_pos pos;

	if (!data->pen_supported || buf[2] != 0x00 || buf[3] != 0x00)
		return false;

	if (buf[0] == 0x00 && buf[1] == 0x00 && data->pen_down) {
		data->pen_up_count++;
		if (data->pen_up_count == 6) {
			data->pen_down = false;
			goto sync;
		}
		return true;
	}

	if (buf[0] == 0x01 && buf[1] == 0x08) {
		touchscreen_set_mt_pos(&pos, &data->prop,
			get_unaligned_le16(&coord[SILEAD_POINT_X_OFF]) & 0xfff,
			get_unaligned_le16(&coord[SILEAD_POINT_Y_OFF]) & 0xfff);

		input_report_abs(data->pen_input, ABS_X, pos.x);
		input_report_abs(data->pen_input, ABS_Y, pos.y);

		data->pen_up_count = 0;
		data->pen_down = true;
		goto sync;
	}

	return false;

sync:
	input_report_key(data->pen_input, BTN_TOOL_PEN, data->pen_down);
	input_report_key(data->pen_input, BTN_TOUCH, data->pen_down);
	input_sync(data->pen_input);
	return true;
}

static void silead_ts_read_data(struct i2c_client *client)
{
	struct silead_ts_data *data = i2c_get_clientdata(client);
	struct input_dev *input = data->input;
	struct device *dev = &client->dev;
	u8 *bufp, buf[SILEAD_TS_DATA_LEN];
	int touch_nr, softbutton, error, i;
	bool softbutton_pressed = false;

	error = i2c_smbus_read_i2c_block_data(client, SILEAD_REG_DATA,
					      SILEAD_TS_DATA_LEN, buf);
	if (error < 0) {
		dev_err(dev, "Data read error %d\n", error);
		return;
	}

	if (buf[0] > SILEAD_MAX_FINGERS) {
		dev_warn(dev, "More touches reported then supported %d > %d\n",
			 buf[0], SILEAD_MAX_FINGERS);
		buf[0] = SILEAD_MAX_FINGERS;
	}

	if (silead_ts_handle_pen_data(data, buf))
		goto sync; /* Pen is down, release all previous touches */

	touch_nr = 0;
	bufp = buf + SILEAD_POINT_DATA_LEN;
	for (i = 0; i < buf[0]; i++, bufp += SILEAD_POINT_DATA_LEN) {
		softbutton = (bufp[SILEAD_POINT_Y_MSB_OFF] &
			      SILEAD_EXTRA_DATA_MASK) >> 4;

		if (softbutton) {
			/*
			 * For now only respond to softbutton == 0x01, some
			 * tablets *without* a capacative button send 0x04
			 * when crossing the edges of the screen.
			 */
			if (softbutton == 0x01)
				softbutton_pressed = true;

			continue;
		}

		/*
		 * Bits 4-7 are the touch id, note not all models have
		 * hardware touch ids so atm we don't use these.
		 */
		data->id[touch_nr] = (bufp[SILEAD_POINT_X_MSB_OFF] &
				      SILEAD_EXTRA_DATA_MASK) >> 4;
		touchscreen_set_mt_pos(&data->pos[touch_nr], &data->prop,
			get_unaligned_le16(&bufp[SILEAD_POINT_X_OFF]) & 0xfff,
			get_unaligned_le16(&bufp[SILEAD_POINT_Y_OFF]) & 0xfff);
		touch_nr++;
	}

	input_mt_assign_slots(input, data->slots, data->pos, touch_nr, 0);

	for (i = 0; i < touch_nr; i++) {
		input_mt_slot(input, data->slots[i]);
		input_mt_report_slot_state(input, MT_TOOL_FINGER, true);
		input_report_abs(input, ABS_MT_POSITION_X, data->pos[i].x);
		input_report_abs(input, ABS_MT_POSITION_Y, data->pos[i].y);

		dev_dbg(dev, "x=%d y=%d hw_id=%d sw_id=%d\n", data->pos[i].x,
			data->pos[i].y, data->id[i], data->slots[i]);
	}

sync:
	input_mt_sync_frame(input);
	input_report_key(input, KEY_LEFTMETA, softbutton_pressed);
	input_sync(input);
}


static int pf_stock_write(struct i2c_client *client, u8 reg,
                          const u8 *data, unsigned int len)
{
	u8 buffer[5];
	int ret;

	if (!len || len > sizeof(buffer) - 1)
		return -EINVAL;
	buffer[0] = reg;
	memcpy(buffer + 1, data, len);
	ret = i2c_master_send(client, buffer, len + 1);
	if (ret != len + 1)
		dev_err(&client->dev, "PF touchscreen control reg=%02x len=%u rc=%d\n",
			reg, len, ret);
	dev_dbg(&client->dev, "PF touchscreen write reg=%02x first=%02x len=%u rc=%d\n",
		 reg, data[0], len, ret);
	return ret == len + 1 ? 0 : ret < 0 ? ret : -EIO;
}

static int pf_stock_detect(struct i2c_client *client)
{
	u8 zero = 0;
	struct i2c_msg message = { .addr = client->addr, .flags = 0,
		.len = 1, .buf = &zero };
	int attempt, ret = -EIO;

	for (attempt = 1; attempt <= 2; attempt++) {
		ret = i2c_transfer(client->adapter, &message, 1);
		dev_dbg(&client->dev, "PF touchscreen detect byte=00 attempt=%d rc=%d\n",
			 attempt, ret);
		if (ret == 1)
			return 0;
		msleep(50);
	}
	dev_err(&client->dev, "PF touchscreen detect failed after 2 attempts rc=%d\n", ret);
	return ret < 0 ? ret : -EIO;
}

static int silead_ts_init(struct i2c_client *client)
{
	static const u8 sequence[][3] = {
		{ 0xe0, 0x88, 20 }, { 0x80, 0x03, 5 },
		{ 0xe4, 0x04, 5 }, { 0xe0, 0x00, 20 },
	};
	int i, ret;

	for (i = 0; i < ARRAY_SIZE(sequence); i++) {
		ret = pf_stock_write(client, sequence[i][0], &sequence[i][1], 1);
		if (ret)
			return ret;
		msleep(sequence[i][2]);
	}
	return 0;
}

static int silead_ts_reset(struct i2c_client *client)
{
	u8 reset = 0x88, clock = 0x04, zero[4] = { 0 };
	int ret;

	ret = pf_stock_write(client, 0xe0, &reset, 1);
	if (ret)
		return ret;
	msleep(10);
	ret = pf_stock_write(client, 0xe4, &clock, 1);
	if (ret)
		return ret;
	msleep(10);
	ret = pf_stock_write(client, 0xbc, zero, sizeof(zero));
	if (ret)
		return ret;
	msleep(10);
	return 0;
}

static int silead_ts_startup(struct i2c_client *client)
{
	u8 zero = 0;
	int ret = pf_stock_write(client, 0xe0, &zero, 1);

	if (ret)
		return ret;
	msleep(10);
	return 0;
}

static int silead_ts_load_fw(struct i2c_client *client)
{
	struct device *dev = &client->dev;
	struct silead_ts_data *data = i2c_get_clientdata(client);
	const struct firmware *fw = NULL;
	struct silead_fw_data *fw_data;
	unsigned int fw_size, i;
	int error;

	dev_dbg(dev, "Firmware file name: %s", data->fw_name);

	/*
	 * Unfortunately, at the time of writing this comment, we have been unable to
	 * get permission from Silead, or from device OEMs, to distribute the necessary
	 * Silead firmware files in linux-firmware.
	 *
	 * On a whole bunch of devices the UEFI BIOS code contains a touchscreen driver,
	 * which contains an embedded copy of the firmware. The fw-loader code has a
	 * "platform" fallback mechanism, which together with info on the firmware
	 * from drivers/platform/x86/touchscreen_dmi.c will use the firmware from the
	 * UEFI driver when the firmware is missing from /lib/firmware. This makes the
	 * touchscreen work OOTB without users needing to manually download the firmware.
	 *
	 * The firmware bundled with the original Windows/Android is usually newer then
	 * the firmware in the UEFI driver and it is better calibrated. This better
	 * calibration can lead to significant differences in the reported min/max
	 * coordinates.
	 *
	 * To deal with this we first try to load the firmware without "platform"
	 * fallback. If that fails we retry with "platform" fallback and if that
	 * succeeds we apply an (optional) set of alternative min/max values from the
	 * "silead,efi-fw-min-max" property.
	 */
	error = firmware_request_nowarn(&fw, data->fw_name, dev);
	if (error) {
		error = firmware_request_platform(&fw, data->fw_name, dev);
		if (error) {
			dev_err(dev, "Firmware request error %d\n", error);
			return error;
		}

		error = device_property_read_u32_array(dev, "silead,efi-fw-min-max",
						       data->efi_fw_min_max,
						       ARRAY_SIZE(data->efi_fw_min_max));
		if (!error)
			data->efi_fw_min_max_set = true;

		/* The EFI (platform) embedded fw does not have pen support */
		if (data->pen_supported) {
			dev_warn(dev, "Warning loading '%s' from filesystem failed, using EFI embedded copy.\n",
				 data->fw_name);
			dev_warn(dev, "Warning pen support is known to be broken in the EFI embedded fw version\n");
			data->pen_supported = false;
		}
	}

	fw_size = fw->size / sizeof(*fw_data);
	fw_data = (struct silead_fw_data *)fw->data;

	for (i = 0; i < fw_size; i++) {
		error = i2c_smbus_write_i2c_block_data(client,
						       fw_data[i].offset,
						       4,
						       (u8 *)&fw_data[i].val);
		if (error) {
			dev_err(dev, "PF touchscreen firmware record=%u reg=%02x rc=%d\n", i, fw_data[i].offset, error);
			break;
		}
		if (!(i % 256) || i + 1 == fw_size)
			dev_dbg(dev, "PF touchscreen firmware progress=%u/%u rc=0\n", i + 1, fw_size);
	}

	release_firmware(fw);
	return error ?: 0;
}

static u32 silead_ts_get_status(struct i2c_client *client)
{
	int error;
	__le32 status;

	error = i2c_smbus_read_i2c_block_data(client, SILEAD_REG_STATUS,
					      sizeof(status), (u8 *)&status);
	if (error < 0) {
		dev_err(&client->dev, "Status read error %d\n", error);
		return error;
	}

	return le32_to_cpu(status);
}

static int silead_ts_get_id(struct i2c_client *client)
{
	struct silead_ts_data *data = i2c_get_clientdata(client);
	__le32 chip_id;
	int error;

	error = i2c_smbus_read_i2c_block_data(client, SILEAD_REG_ID,
					      sizeof(chip_id), (u8 *)&chip_id);
	if (error < 0)
		return error;

	data->chip_id = le32_to_cpu(chip_id);
	dev_info(&client->dev, "Silead chip ID: 0x%8X", data->chip_id);

	return 0;
}

static int silead_ts_setup(struct i2c_client *client)
{
	struct silead_ts_data *data = i2c_get_clientdata(client);
	int ret;
	u32 status;

	dev_dbg(&client->dev, "PF touchscreen: PH1 already high before LDO enable; adapter clock unchanged by touch module\n");
	msleep(20);
	gpiod_set_value_cansleep(data->gpio_power, 1);
	msleep(5);
	ret = pf_stock_detect(client);
	if (ret)
		return ret;
	gpiod_set_value_cansleep(data->gpio_power, 1);
	msleep(25);
	silead_ts_set_power(client, SILEAD_POWER_OFF);
	silead_ts_set_power(client, SILEAD_POWER_ON);
	dev_dbg(&client->dev, "PF touchscreen: detect completed; PH1 low55/high35; control init, no ID read\n");
	ret = silead_ts_init(client);
	if (ret)
		return ret;
	ret = silead_ts_reset(client);
	if (ret)
		return ret;
	ret = silead_ts_load_fw(client);
	if (ret)
		return ret;
	ret = silead_ts_startup(client);
	if (ret)
		return ret;
	ret = silead_ts_reset(client);
	if (ret)
		return ret;
	ret = silead_ts_startup(client);
	if (ret)
		return ret;
	status = silead_ts_get_status(client);
	if (status != SILEAD_STATUS_OK) {
		dev_err(&client->dev, "PF touchscreen initialization status=%08x expected=%08x\n",
			status, SILEAD_STATUS_OK);
		return -ENODEV;
	}
	dev_info(&client->dev, "PF touchscreen firmware ready status=%08x\n", status);
	return silead_ts_get_id(client);
}

static irqreturn_t silead_ts_threaded_irq_handler(int irq, void *id)
{
	struct silead_ts_data *data = id;
	struct i2c_client *client = data->client;

	silead_ts_read_data(client);

	return IRQ_HANDLED;
}

static void silead_ts_read_props(struct i2c_client *client)
{
	struct silead_ts_data *data = i2c_get_clientdata(client);
	struct device *dev = &client->dev;
	const char *str;
	int error;

	error = device_property_read_string(dev, "firmware-name", &str);
	if (!error)
		snprintf(data->fw_name, sizeof(data->fw_name),
			 "silead/%s", str);
	else
		dev_dbg(dev, "Firmware file name read error. Using default.");

	data->pen_supported = device_property_read_bool(dev, "silead,pen-supported");
	device_property_read_u32(dev, "silead,pen-resolution-x", &data->pen_x_res);
	device_property_read_u32(dev, "silead,pen-resolution-y", &data->pen_y_res);
}

#ifdef CONFIG_ACPI
static int silead_ts_set_default_fw_name(struct silead_ts_data *data,
					 const struct i2c_device_id *id)
{
	const struct acpi_device_id *acpi_id;
	struct device *dev = &data->client->dev;
	int i;

	if (ACPI_HANDLE(dev)) {
		acpi_id = acpi_match_device(dev->driver->acpi_match_table, dev);
		if (!acpi_id)
			return -ENODEV;

		snprintf(data->fw_name, sizeof(data->fw_name),
			 "silead/%s.fw", acpi_id->id);

		for (i = 0; i < strlen(data->fw_name); i++)
			data->fw_name[i] = tolower(data->fw_name[i]);
	} else {
		snprintf(data->fw_name, sizeof(data->fw_name),
			 "silead/%s.fw", id->name);
	}

	return 0;
}
#else
static int silead_ts_set_default_fw_name(struct silead_ts_data *data,
					 const struct i2c_device_id *id)
{
	snprintf(data->fw_name, sizeof(data->fw_name),
		 "silead/%s.fw", id->name);
	return 0;
}
#endif

static void silead_disable_regulator(void *arg)
{
	struct silead_ts_data *data = arg;

	regulator_bulk_disable(data->num_regulators, data->regulators);
}

static int silead_pf1007l_set_power_voltage(struct silead_ts_data *data)
{
	struct regulator *power = data->regulators[0].consumer;
	int ret;

	ret = regulator_set_voltage(power, 3300000, 3300000);
	if (ret)
		return ret;
	ret = regulator_get_voltage(power);
	if (ret < 0)
		return ret;
	return ret == 3300000 ? 0 : -EINVAL;
}

static int silead_ts_probe(struct i2c_client *client)
{
	const struct i2c_device_id *id = i2c_client_get_device_id(client);
	struct silead_ts_data *data;
	struct device *dev = &client->dev;
	int error;

	if (!i2c_check_functionality(client->adapter,
				     I2C_FUNC_I2C |
				     I2C_FUNC_SMBUS_READ_I2C_BLOCK |
				     I2C_FUNC_SMBUS_WRITE_I2C_BLOCK)) {
		dev_err(dev, "I2C functionality check failed\n");
		return -ENXIO;
	}

	data = devm_kzalloc(dev, sizeof(*data), GFP_KERNEL);
	if (!data)
		return -ENOMEM;

	i2c_set_clientdata(client, data);
	data->client = client;

	data->pf1007l = of_device_is_compatible(dev->of_node, "pf1007l,gsl-m86-hd");
	if (!data->pf1007l)
		return -ENODEV;
	if (data->pf1007l) {
		strscpy(data->fw_name, "silead/pf1007l-gsl-m86-hd.fw", sizeof(data->fw_name));
	} else {
		error = silead_ts_set_default_fw_name(data, id);
		if (error)
			return error;
	}

	silead_ts_read_props(client);

	/* We must have the IRQ provided by DT or ACPI subsystem */
	if (client->irq <= 0)
		return -ENODEV;

	if (data->pf1007l) {
		/* The stock board controls one rail; its internal pin wiring is unknown. */
		if (!device_property_present(dev, "power-supply"))
			return -EINVAL;
		data->num_regulators = 1;
		data->regulators[0].supply = "power";
	} else {
		data->num_regulators = ARRAY_SIZE(data->regulators);
		data->regulators[0].supply = "vddio";
		data->regulators[1].supply = "avdd";
	}
	error = devm_regulator_bulk_get(dev, data->num_regulators,
					data->regulators);
	if (error)
		return error;

	if (data->pf1007l) {
		error = silead_pf1007l_set_power_voltage(data);
		if (error)
			return dev_err_probe(dev, error, "touch supply must be 3300000 uV before enable\n");
	}

	/* Power GPIO pin */
	data->gpio_power = devm_gpiod_get(dev, "power", GPIOD_OUT_HIGH);
	if (IS_ERR(data->gpio_power))
		return dev_err_probe(dev, PTR_ERR(data->gpio_power),
				     "Shutdown GPIO request failed\n");

	dev_dbg(dev, "PF touchscreen: PH1 high; enabling qualified 3300000 uV supply\n");

	/*
	 * Enable regulators at probe and disable them at remove, we need
	 * to keep the chip powered otherwise it forgets its firmware.
	 */
	error = regulator_bulk_enable(data->num_regulators,
				      data->regulators);
	if (error)
		return error;

	error = devm_add_action_or_reset(dev, silead_disable_regulator, data);
	if (error)
		return error;

	error = silead_ts_setup(client);
	if (error)
		return error;

	error = silead_ts_request_input_dev(data);
	if (error)
		return error;

	error = silead_ts_request_pen_input_dev(data);
	if (error)
		return error;

	error = devm_request_threaded_irq(dev, client->irq,
					  NULL, silead_ts_threaded_irq_handler,
					  IRQF_ONESHOT, client->name, data);
	if (error) {
		if (error != -EPROBE_DEFER)
			dev_err(dev, "IRQ request failed %d\n", error);
		return error;
	}

	return 0;
}

static int silead_ts_suspend(struct device *dev)
{
	struct i2c_client *client = to_i2c_client(dev);

	disable_irq(client->irq);
	silead_ts_set_power(client, SILEAD_POWER_OFF);
	return 0;
}

static int silead_ts_resume(struct device *dev)
{
	struct i2c_client *client = to_i2c_client(dev);
	bool second_try = false;
	int error, status;

	silead_ts_set_power(client, SILEAD_POWER_ON);

 retry:
	error = silead_ts_reset(client);
	if (error)
		return error;

	if (second_try) {
		error = silead_ts_load_fw(client);
		if (error)
			return error;
	}

	error = silead_ts_startup(client);
	if (error)
		return error;

	status = silead_ts_get_status(client);
	if (status != SILEAD_STATUS_OK) {
		if (!second_try) {
			second_try = true;
			dev_dbg(dev, "Reloading firmware after unsuccessful resume\n");
			goto retry;
		}
		dev_err(dev, "Resume error, status: 0x%02x\n", status);
		return -ENODEV;
	}

	enable_irq(client->irq);

	return 0;
}

static DEFINE_SIMPLE_DEV_PM_OPS(silead_ts_pm, silead_ts_suspend, silead_ts_resume);

static const struct i2c_device_id silead_ts_id[] = {
	{ }
};
MODULE_DEVICE_TABLE(i2c, silead_ts_id);


#ifdef CONFIG_OF
static const struct of_device_id silead_ts_of_match[] = {
	{ .compatible = "pf1007l,gsl-m86-hd" },
	{ },
};
MODULE_DEVICE_TABLE(of, silead_ts_of_match);
#endif

static struct i2c_driver silead_ts_driver = {
	.probe = silead_ts_probe,
	.id_table = silead_ts_id,
	.driver = {
		.name = SILEAD_TS_NAME,
		.of_match_table = of_match_ptr(silead_ts_of_match),
		.pm = pm_sleep_ptr(&silead_ts_pm),
	},
};
module_i2c_driver(silead_ts_driver);

MODULE_AUTHOR("Robert Dolca <robert.dolca@intel.com>");
MODULE_DESCRIPTION("PF1007L Silead touchscreen with qualified stock startup");
MODULE_LICENSE("GPL");
