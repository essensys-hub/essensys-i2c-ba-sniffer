#ifndef ESSENSYS_PROGRAMMER_BOARD_CONTRACT_H
#define ESSENSYS_PROGRAMMER_BOARD_CONTRACT_H

/* Provisional integrated-board GPIO contract; not a qualification switch.
 * TODO(agent): qualify electrical adapters before exposing protocol operations.
 * Do not run the historical capture UF2 on this integrated pin assignment.
 */
#define BA_PGC_PIN 0u
#define BA_PGD_OUT_PIN 1u
#define BA_PGD_IN_PIN 2u
#define BA_PGD_DIR_PIN 3u
#define BA_OE_PIN 4u
#define BA_VPP_EN_PIN 5u
#define BP_DSCLK_PIN 8u
#define BP_DSI_PIN 9u
#define BP_DSO_PIN 10u
#define BP_BKPT_PIN 11u
#define BP_RESET_PIN 12u
#define BP_ALLPST_PIN 13u
#define BP_OE_PIN 14u
#define BP_RESET_SENSE_PIN 15u
#define BA_VDD_SENSE_PIN 26u
#define BA_VPP_SENSE_PIN 27u
#define BP_VREF_SENSE_PIN 28u
#endif
