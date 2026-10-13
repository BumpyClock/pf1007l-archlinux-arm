// SPDX-License-Identifier: GPL-2.0-only
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>
#include <drm/drm_probe_helper.h>
#include <video/mipi_display.h>

#include "sq9365-program.h"
#include "sq9365-private-table.h"

enum sq9365_state {
	SQ9365_OFF,
	SQ9365_PREPARED,
	SQ9365_ENABLED,
	SQ9365_FAULT,
};

struct sq9365 {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi;
	struct regulator *dc1sw;
	struct regulator *eldo3;
	struct gpio_desc *reset;
	enum sq9365_state state;
	bool dc1sw_enabled;
	bool eldo3_enabled;
	enum drm_panel_orientation orientation;
};

static struct sq9365 *to_sq9365(struct drm_panel *panel)
{
	return container_of(panel, struct sq9365, panel);
}

static void sq9365_delay(void *context, unsigned int milliseconds)
{
	msleep(milliseconds);
}

static int sq9365_write(void *context, unsigned int index, u8 type,
			const u8 *bytes, size_t count)
{
	struct sq9365 *ctx = context;
	ssize_t ret;

	if ((count == 1 && type != MIPI_DSI_DCS_SHORT_WRITE) ||
	    (count == 2 && type != MIPI_DSI_DCS_SHORT_WRITE_PARAM) ||
	    (count > 2 && type != MIPI_DSI_DCS_LONG_WRITE))
		return -EINVAL;
	ret = mipi_dsi_dcs_write_buffer(ctx->dsi, bytes, count);
	if (ret < 0 || (size_t)ret != count) {
		dev_err(&ctx->dsi->dev,
			"DCS record %u type 0x%02x count %zu result %zd\n",
			index, type, count, ret);
		return ret < 0 ? ret : -EIO;
	}
	return 0;
}

static int sq9365_power_action(void *context, enum sq9365_power_action action,
			       unsigned int milliseconds)
{
	struct sq9365 *ctx = context;
	int ret;

	switch (action) {
	case SQ9365_DC1SW_ON:
		ret = regulator_enable(ctx->dc1sw);
		if (!ret)
			ctx->dc1sw_enabled = true;
		return ret;
	case SQ9365_ELDO3_ON:
		ret = regulator_enable(ctx->eldo3);
		if (!ret)
			ctx->eldo3_enabled = true;
		return ret;
	case SQ9365_RESET_HIGH:
		return gpiod_direction_output(ctx->reset, 0);
	case SQ9365_RESET_LOW:
		return gpiod_direction_output(ctx->reset, 1);
	case SQ9365_WAIT:
		msleep(milliseconds);
		return 0;
	}
	return -EINVAL;
}

static int sq9365_power_off(struct sq9365 *ctx)
{
	int ret, first = 0;

	ret = gpiod_direction_output(ctx->reset, 1);
	if (ret)
		first = ret;
	msleep(20);
	msleep(30);
	if (ctx->eldo3_enabled) {
		ret = regulator_disable(ctx->eldo3);
		if (!ret)
			ctx->eldo3_enabled = false;
		else if (!first)
			first = ret;
	}
	if (ctx->dc1sw_enabled) {
		ret = regulator_disable(ctx->dc1sw);
		if (!ret)
			ctx->dc1sw_enabled = false;
		else if (!first)
			first = ret;
	}
	msleep(50);
	return first;
}

static int sq9365_prepare(struct drm_panel *panel)
{
	struct sq9365 *ctx = to_sq9365(panel);
	const struct sq9365_transport transport = {
		.write = sq9365_write,
		.delay = sq9365_delay,
		.context = ctx,
	};
	int ret;

	if (ctx->state == SQ9365_FAULT)
		return -EIO;
	if (ctx->state != SQ9365_OFF)
		return 0;
	if (ctx->dc1sw_enabled || ctx->eldo3_enabled)
		return -EBUSY;
	ret = sq9365_run_power(sq9365_power_action, ctx);
	if (!ret)
		ret = sq9365_execute(sq9365_program, ARRAY_SIZE(sq9365_program),
				     &transport);
	if (ret) {
		int cleanup = sq9365_power_off(ctx);

		if (cleanup)
			ctx->state = SQ9365_FAULT;
		dev_err(&ctx->dsi->dev, "prepare failed %d, cleanup %d\n",
			ret, cleanup);
		return ret;
	}
	msleep(150);
	ctx->state = SQ9365_PREPARED;
	dev_info(&ctx->dsi->dev, "204 records complete in LP DCS; prepared\n");
	return 0;
}

static int sq9365_enable(struct drm_panel *panel)
{
	struct sq9365 *ctx = to_sq9365(panel);

	if (ctx->state != SQ9365_PREPARED && ctx->state != SQ9365_ENABLED)
		return -EIO;
	if (ctx->state == SQ9365_ENABLED)
		return 0;
	/* sun6i enables panels before HS video; brightness must remain zero. */
	msleep(400);
	ctx->state = SQ9365_ENABLED;
	dev_info(&ctx->dsi->dev,
		 "enabled; scanout and manual backlight trial still unverified\n");
	return 0;
}

static int sq9365_disable(struct drm_panel *panel)
{
	struct sq9365 *ctx = to_sq9365(panel);

	if (ctx->state == SQ9365_ENABLED)
		ctx->state = SQ9365_PREPARED;
	return 0;
}

static int sq9365_unprepare(struct drm_panel *panel)
{
	struct sq9365 *ctx = to_sq9365(panel);
	int ret;

	if (ctx->state == SQ9365_OFF)
		return 0;
	if (ctx->state == SQ9365_ENABLED)
		return -EBUSY;
	ret = sq9365_power_off(ctx);
	ctx->state = ret ? SQ9365_FAULT : SQ9365_OFF;
	return ret;
}

static const struct drm_display_mode sq9365_mode = {
	.clock = SQ9365_CLOCK_KHZ,
	.hdisplay = SQ9365_HDISPLAY,
	.hsync_start = SQ9365_HSYNC_START,
	.hsync_end = SQ9365_HSYNC_END,
	.htotal = SQ9365_HTOTAL,
	.vdisplay = SQ9365_VDISPLAY,
	.vsync_start = SQ9365_VSYNC_START,
	.vsync_end = SQ9365_VSYNC_END,
	.vtotal = SQ9365_VTOTAL,
	.width_mm = SQ9365_WIDTH_MM,
	.height_mm = SQ9365_HEIGHT_MM,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

static int sq9365_get_modes(struct drm_panel *panel,
			    struct drm_connector *connector)
{
	struct sq9365 *ctx = to_sq9365(panel);
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, &sq9365_mode);
	if (!mode)
		return -ENOMEM;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);
	connector->display_info.width_mm = mode->width_mm;
	connector->display_info.height_mm = mode->height_mm;
	drm_connector_set_panel_orientation(connector, ctx->orientation);
	return 1;
}

static const struct drm_panel_funcs sq9365_panel_funcs = {
	.prepare = sq9365_prepare,
	.enable = sq9365_enable,
	.disable = sq9365_disable,
	.unprepare = sq9365_unprepare,
	.get_modes = sq9365_get_modes,
};

static bool sq9365_supply_is_preserved(struct device_node *node,
				       const char *property)
{
	struct device_node *supply = of_parse_phandle(node, property, 0);
	bool preserved;

	if (!supply)
		return false;
	preserved = of_property_read_bool(supply, "regulator-always-on");
	of_node_put(supply);
	return preserved;
}

static int sq9365_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct sq9365 *ctx;
	int ret;

	if (!of_property_read_bool(dev->of_node,
				   "yhk,power-sequence-qualified"))
		return dev_err_probe(dev, -EPERM,
				     "board power qualification absent; no GPIO/rail writes\n");
	/* sun6i unprepares before PHY power-off: do not physically cut rails. */
	if (!sq9365_supply_is_preserved(dev->of_node, "dc1sw-supply") ||
	    !sq9365_supply_is_preserved(dev->of_node, "eldo3-supply"))
		return dev_err_probe(dev, -EPERM,
				     "both real panel supplies must be preserved always-on\n");
	ret = sq9365_validate(sq9365_program, ARRAY_SIZE(sq9365_program));
	if (ret)
		return ret;
	ctx = devm_drm_panel_alloc(dev, struct sq9365, panel,
				   &sq9365_panel_funcs, DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(ctx))
		return PTR_ERR(ctx);
	ctx->dsi = dsi;
	ctx->dc1sw = devm_regulator_get(dev, "dc1sw");
	if (IS_ERR(ctx->dc1sw))
		return dev_err_probe(dev, PTR_ERR(ctx->dc1sw), "dc1sw supply\n");
	ctx->eldo3 = devm_regulator_get(dev, "eldo3");
	if (IS_ERR(ctx->eldo3))
		return dev_err_probe(dev, PTR_ERR(ctx->eldo3), "eldo3 supply\n");
	ctx->reset = devm_gpiod_get(dev, "reset", GPIOD_ASIS);
	if (IS_ERR(ctx->reset))
		return dev_err_probe(dev, PTR_ERR(ctx->reset), "reset GPIO\n");
	if (!gpiod_is_active_low(ctx->reset))
		return dev_err_probe(dev, -EINVAL, "reset must be active low\n");
	ret = of_drm_get_panel_orientation(dev->of_node, &ctx->orientation);
	if (ret)
		return ret;
	mipi_dsi_set_drvdata(dsi, ctx);
	dsi->lanes = 4;
	dsi->format = MIPI_DSI_FMT_RGB888;
	dsi->mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_LPM;
	ctx->panel.prepare_prev_first = true;
	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return ret;
	drm_panel_add(&ctx->panel);
	ret = mipi_dsi_attach(dsi);
	if (ret) {
		drm_panel_remove(&ctx->panel);
		return ret;
	}
	dev_info(dev, "SQ9365 candidate attached, 4-lane RGB888 800x1280\n");
	return 0;
}

static void sq9365_remove(struct mipi_dsi_device *dsi)
{
	struct sq9365 *ctx = mipi_dsi_get_drvdata(dsi);

	mipi_dsi_detach(dsi);
	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id sq9365_of_match[] = {
	{ .compatible = "yhk,zr789-sq9365-101" },
	{ }
};
MODULE_DEVICE_TABLE(of, sq9365_of_match);

static struct mipi_dsi_driver sq9365_driver = {
	.probe = sq9365_probe,
	.remove = sq9365_remove,
	.driver = {
		.name = "panel-yhk-sq9365",
		.of_match_table = sq9365_of_match,
	},
};
module_mipi_dsi_driver(sq9365_driver);

MODULE_DESCRIPTION("Local experimental YHK ZR789 SQ9365 800x1280 DSI panel");
MODULE_AUTHOR("Photoframe display-port contributors");
MODULE_LICENSE("GPL");
