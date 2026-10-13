// SPDX-License-Identifier: GPL-2.0-only
/*
 * RSB driver for the X-Powers' Power Management ICs
 *
 * AXP20x typically comprises an adaptive USB-Compatible PWM charger, BUCK DC-DC
 * converters, LDOs, multiple 12-bit ADCs of voltage, current and temperature
 * as well as configurable GPIOs.
 *
 * This driver supports the RSB variants.
 *
 * Copyright (C) 2015 Chen-Yu Tsai
 *
 * Author: Chen-Yu Tsai <wens@csie.org>
 */

#include <linux/acpi.h>
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/mfd/axp20x.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/sunxi-rsb.h>

static int pf1007l_check_cold_power(struct axp20x_dev *axp20x)
{
	static const struct { u8 reg; u8 value; } cold[] = {
		{ 0x03, 0x06 }, { 0x10, 0xef }, { 0x12, 0x80 }, { 0x13, 0x81 },
		{ 0x15, 0x00 }, { 0x16, 0x00 }, { 0x1b, 0x00 }, { 0x21, 0x0e },
		{ 0x22, 0x19 }, { 0x23, 0x1e }, { 0x24, 0x19 }, { 0x25, 0x0a },
		{ 0x90, 0x02 }, { 0x92, 0x02 }, { 0x93, 0x1f }, { 0x94, 0x01 },
	};
	unsigned int value;
	int i, ret;

	for (i = 0; i < ARRAY_SIZE(cold); i++) {
		ret = regmap_read(axp20x->regmap, cold[i].reg, &value);
		if (ret)
			return ret;
		if (value != cold[i].value)
			return dev_err_probe(axp20x->dev, -EINVAL,
				"PF1007L cold power mismatch %02x=%02x expected %02x; no rail changes\n",
				cold[i].reg, value, cold[i].value);
	}
	/* DC1SW is already enabled at 3.0 V; preserve the stock settling gap. */
	msleep(10);
	dev_info(axp20x->dev, "PF1007L cold power verified; registering controlled rails\n");
	return 0;
}

static int axp20x_rsb_probe(struct sunxi_rsb_device *rdev)
{
	struct axp20x_dev *axp20x;
	int ret;

	axp20x = devm_kzalloc(&rdev->dev, sizeof(*axp20x), GFP_KERNEL);
	if (!axp20x)
		return -ENOMEM;

	axp20x->dev = &rdev->dev;
	axp20x->irq = rdev->irq;
	dev_set_drvdata(&rdev->dev, axp20x);

	ret = axp20x_match_device(axp20x);
	if (ret)
		return ret;

	axp20x->regmap = devm_regmap_init_sunxi_rsb(rdev, axp20x->regmap_cfg);
	if (IS_ERR(axp20x->regmap)) {
		ret = PTR_ERR(axp20x->regmap);
		dev_err(&rdev->dev, "regmap init failed: %d\n", ret);
		return ret;
	}

	if (of_device_is_compatible(rdev->dev.of_node, "pf1007l,axp223-active")) {
		ret = pf1007l_check_cold_power(axp20x);
		if (ret)
			return ret;
	}

	return axp20x_device_probe(axp20x);
}

static void axp20x_rsb_remove(struct sunxi_rsb_device *rdev)
{
	struct axp20x_dev *axp20x = sunxi_rsb_device_get_drvdata(rdev);

	axp20x_device_remove(axp20x);
}

static const struct of_device_id axp20x_rsb_of_match[] = {
	{ .compatible = "x-powers,axp223", .data = (void *)AXP223_ID },
	{ .compatible = "x-powers,axp717", .data = (void *)AXP717_ID },
	{ .compatible = "x-powers,axp803", .data = (void *)AXP803_ID },
	{ .compatible = "x-powers,axp806", .data = (void *)AXP806_ID },
	{ .compatible = "x-powers,axp809", .data = (void *)AXP809_ID },
	{ .compatible = "x-powers,axp813", .data = (void *)AXP813_ID },
	{ },
};
MODULE_DEVICE_TABLE(of, axp20x_rsb_of_match);

static struct sunxi_rsb_driver axp20x_rsb_driver = {
	.driver = {
		.name	= "axp20x-rsb",
		.of_match_table	= of_match_ptr(axp20x_rsb_of_match),
	},
	.probe	= axp20x_rsb_probe,
	.remove	= axp20x_rsb_remove,
};
module_sunxi_rsb_driver(axp20x_rsb_driver);

MODULE_DESCRIPTION("PMIC MFD sunXi RSB driver for AXP20X");
MODULE_AUTHOR("Chen-Yu Tsai <wens@csie.org>");
MODULE_LICENSE("GPL v2");
