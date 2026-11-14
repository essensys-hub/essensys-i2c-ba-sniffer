/* USB diagnostic identity uses the Pico SDK development VID/PID, not a
 * production allocation. Obtain a product identity before distribution.
 * Unlike the SDK default (250 mA), request one USB2 unit load (100 mA).
 * This descriptor is a budget contract; measured current/suspend compliance
 * remains a hardware qualification requirement.
 */
#include "tusb.h"
#include <string.h>

static const tusb_desc_device_t device = {
    .bLength = sizeof(tusb_desc_device_t), .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200, .bDeviceClass = TUSB_CLASS_MISC,
    .bDeviceSubClass = MISC_SUBCLASS_COMMON, .bDeviceProtocol = MISC_PROTOCOL_IAD,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = 0x2e8a, .idProduct = 0x0009, .bcdDevice = 0x0001,
    .iManufacturer = 1, .iProduct = 2, .iSerialNumber = 0, .bNumConfigurations = 1
};

static const uint8_t config[] = {
    TUD_CONFIG_DESCRIPTOR(1, 2, 0, TUD_CONFIG_DESC_LEN + TUD_CDC_DESC_LEN, 0, 100),
    TUD_CDC_DESCRIPTOR(0, 0, 0x81, 8, 0x02, 0x82, 64)
};

const uint8_t *tud_descriptor_device_cb(void) { return (const uint8_t *)&device; }
const uint8_t *tud_descriptor_configuration_cb(uint8_t index) {
    return index == 0 ? config : NULL;
}

const uint16_t *tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
    (void)langid;
    static uint16_t buffer[32];
    size_t length;
    if (index == 0) {
        buffer[1] = 0x0409;
        length = 1;
    } else {
        const char *s = index == 1 ? "Essensys development" :
                        index == 2 ? "Programmer diagnostic" : NULL;
        if (!s) return NULL;
        length = strlen(s);
        if (length > 31) length = 31;
        for (size_t i = 0; i < length; ++i) buffer[1 + i] = (uint8_t)s[i];
    }
    buffer[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * length + 2));
    return buffer;
}
