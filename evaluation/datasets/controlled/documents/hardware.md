# Harbor workstation

The Harbor copilot is developed on a constrained laptop.

MARKER_HW_RAM: The Harbor workstation has 8 GB of RAM and no discrete GPU.

MARKER_HW_IGPU: Graphics on the Harbor laptop are Intel integrated graphics, so embedding and chat must stay CPU-first.

Do not assume a large local model will fit next to the operating system and two Python processes.
