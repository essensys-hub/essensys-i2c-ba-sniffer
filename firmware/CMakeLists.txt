cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2 CACHE STRING "Carte cible")
if(NOT DEFINED ENV{PICO_SDK_PATH} AND NOT PICO_SDK_PATH)
  message(FATAL_ERROR "Définir PICO_SDK_PATH vers le SDK 2.3.1 (voir README).")
endif()
if(NOT PICO_SDK_PATH)
  set(PICO_SDK_PATH $ENV{PICO_SDK_PATH})
endif()
include(${PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(essensys_pico2 C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
pico_sdk_init()
add_executable(essensys_pico2 main.c capture.c capture_config.c)
target_compile_options(essensys_pico2 PRIVATE -Wall -Wextra -Werror)
target_link_libraries(essensys_pico2 pico_stdlib hardware_pio hardware_dma hardware_clocks hardware_watchdog)
pico_enable_stdio_usb(essensys_pico2 1)
pico_enable_stdio_uart(essensys_pico2 0)
pico_set_program_name(essensys_pico2 "essensys-pico2-capture")
pico_set_program_version(essensys_pico2 "0.1.0")
pico_add_extra_outputs(essensys_pico2)

# The integrated board uses the FX2 for acquisition. This distinct image is a
# guarded USB diagnostic, with protocol cores compiled for native/Arm validation.
add_executable(essensys_programmer
  programmer/main.c programmer/control.c programmer/usb_descriptors.c
  programmer/icsp.c programmer/bdm.c)
target_compile_options(essensys_programmer PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(essensys_programmer PRIVATE
  PICO_STDIO_USB_USE_DEFAULT_DESCRIPTORS=0
  PICO_ENABLE_USB_RESET_VIA_BAUD_RATE=0
  PICO_ENABLE_USB_RESET_VIA_VENDOR_INTERFACE=0)
target_link_libraries(essensys_programmer pico_stdlib hardware_clocks hardware_watchdog)
pico_enable_stdio_usb(essensys_programmer 1)
pico_enable_stdio_uart(essensys_programmer 0)
pico_set_program_name(essensys_programmer "essensys-programmer-diagnostic")
pico_set_program_version(essensys_programmer "0.1.0")
pico_add_extra_outputs(essensys_programmer)
