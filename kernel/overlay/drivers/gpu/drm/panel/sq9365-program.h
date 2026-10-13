/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SQ9365_PROGRAM_H
#define SQ9365_PROGRAM_H

#ifdef __KERNEL__
#include <linux/errno.h>
#include <linux/types.h>
#else
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef uint8_t u8;
typedef uint16_t u16;
#endif

enum sq9365_operation {
	SQ9365_DCS,
	SQ9365_DELAY,
	SQ9365_END,
};

struct sq9365_record {
	enum sq9365_operation operation;
	u16 milliseconds;
	u8 command;
	u8 length;
	u8 payload[64];
};

struct sq9365_transport {
	int (*write)(void *context, unsigned int index, u8 type,
		     const u8 *bytes, size_t count);
	void (*delay)(void *context, unsigned int milliseconds);
	void *context;
};

static inline int sq9365_validate(const struct sq9365_record *records,
				 size_t count)
{
	size_t i;

	if (!records || !count)
		return -EINVAL;
	for (i = 0; i < count; i++) {
		const struct sq9365_record *r = &records[i];

		switch (r->operation) {
		case SQ9365_DCS:
			if (r->length > sizeof(r->payload) || r->milliseconds)
				return -EINVAL;
			break;
		case SQ9365_DELAY:
			if (!r->milliseconds || r->length || r->command)
				return -EINVAL;
			break;
		case SQ9365_END:
			if (i != count - 1 || r->length || r->command ||
			    r->milliseconds)
				return -EINVAL;
			return 0;
		default:
			return -EINVAL;
		}
	}
	return -EINVAL;
}

static inline int sq9365_execute(const struct sq9365_record *records,
				size_t count,
				const struct sq9365_transport *transport)
{
	size_t i;
	int ret = sq9365_validate(records, count);

	if (ret)
		return ret;
	for (i = 0; i < count; i++) {
		const struct sq9365_record *r = &records[i];
		u8 bytes[65], type;

		switch (r->operation) {
		case SQ9365_DCS:
			bytes[0] = r->command;
			for (size_t j = 0; j < r->length; j++)
				bytes[j + 1] = r->payload[j];
			type = r->length == 0 ? 0x05 :
			       r->length == 1 ? 0x15 : 0x39;
			ret = transport->write(transport->context, i, type,
					       bytes, r->length + 1);
			if (ret)
				return ret;
			break;
		case SQ9365_DELAY:
			transport->delay(transport->context, r->milliseconds);
			break;
		case SQ9365_END:
			return 0;
		}
	}
	return -EINVAL;
}

enum sq9365_power_action {
	SQ9365_DC1SW_ON,
	SQ9365_ELDO3_ON,
	SQ9365_RESET_HIGH,
	SQ9365_RESET_LOW,
	SQ9365_WAIT,
};

struct sq9365_power_step {
	enum sq9365_power_action action;
	unsigned int milliseconds;
};

/* Both reset trains occur in the selected stock callback; neither is removed. */
static const struct sq9365_power_step sq9365_power_on[] = {
	{ SQ9365_DC1SW_ON, 0 }, { SQ9365_WAIT, 10 },
	{ SQ9365_ELDO3_ON, 0 }, { SQ9365_WAIT, 50 },
	{ SQ9365_WAIT, 10 },
	{ SQ9365_RESET_HIGH, 0 }, { SQ9365_WAIT, 10 },
	{ SQ9365_RESET_LOW, 0 }, { SQ9365_WAIT, 20 },
	{ SQ9365_RESET_HIGH, 0 }, { SQ9365_WAIT, 50 },
	{ SQ9365_WAIT, 10 },
	{ SQ9365_RESET_HIGH, 0 }, { SQ9365_WAIT, 10 },
	{ SQ9365_RESET_LOW, 0 }, { SQ9365_WAIT, 30 },
	{ SQ9365_RESET_HIGH, 0 }, { SQ9365_WAIT, 30 },
};

static inline int sq9365_run_power(int (*action)(void *,
				   enum sq9365_power_action, unsigned int),
				  void *context)
{
	size_t i;

	for (i = 0; i < sizeof(sq9365_power_on) /
			sizeof(sq9365_power_on[0]); i++) {
		int ret = action(context, sq9365_power_on[i].action,
				 sq9365_power_on[i].milliseconds);

		if (ret)
			return ret;
	}
	return 0;
}

#define SQ9365_CLOCK_KHZ 67000
#define SQ9365_HDISPLAY 800
#define SQ9365_HSYNC_START 818
#define SQ9365_HSYNC_END 836
#define SQ9365_HTOTAL 854
#define SQ9365_VDISPLAY 1280
#define SQ9365_VSYNC_START 1300
#define SQ9365_VSYNC_END 1304
#define SQ9365_VTOTAL 1314
#define SQ9365_WIDTH_MM 135
#define SQ9365_HEIGHT_MM 216

#endif
