# Salon physical release checklist

Release candidate: `0.2.8`
Checklist updated: 2026-08-25  
Status: **not physically verified**

This checklist is a release gate, not a claim based on automated fixtures.
Record exact models, firmware, connection mode, OS and GNOME versions, logs,
and limitations for every row. All required rows must be `PASS` before changing
the overall status to verified.

| Area | Required scenario | Device / environment | Result | Evidence / limitations |
|---|---|---|---|---|
| Controller | DualSense navigation and actions over USB | Sony DualSense `054c:0ce6`, USB; Ubuntu 26.04, GNOME 50.1, libmanette GUID `030000004c050000e60c000011810000` | PARTIAL | Kernel exposed `event15`/`js0`; libmanette identified the PS5 mapping and a 15-second live control sample delivered 2,607 button/axis events. An in-app navigation/action pass is still required |
| Controller | DualSense navigation and actions over Bluetooth | Not connected | UNTESTED | Physical pass required |
| Controller | Xbox Wireless controller | Not connected | UNTESTED | Physical pass required |
| Controller | Switch Pro or 8BitDo, Nintendo button layout | Not connected | UNTESTED | Physical pass required |
| HDMI-CEC | Navigation, OK/BACK/MENU, reconnect, shutdown/startup | Pulse-Eight/libCEC adapter and television not connected | UNTESTED | `cec-client` is not installed locally |
| Bluetooth | Discovery, Just Works pair, reconnect and removal | No test device connected | UNTESTED | Physical pass required |
| Bluetooth | Unsupported PIN-entry device gives an honest failure | No test device connected | UNTESTED | Physical pass required |
| Accessibility | Orca announces screens, focused tiles/rows, Settings controls, disabled controls, search and dialogs | Orca installed; no conducted screen-reader pass | UNTESTED | Human listening pass required |
| Session | Native GNOME Shell login, launch/return, portal input, suspend/power, forced crash and recovery | Ubuntu 26.04 LTS, GNOME Shell 50.1, Wayland | PARTIAL | Current-source Wayland smoke mapped and rendered at 1920×1080, drove system menu/search/Settings, captured a frame, and exited cleanly. Portal, power, and crash-loop passes still require a disposable Salon session |
| Session | GNOME Kiosk login and the same lifecycle scenarios | Kiosk session not entered | UNTESTED | Physical/session pass required |

Automated evidence belongs in the release CI artifacts: native and Flatpak
Wayland smoke captures, pytest output, Meson negative dependency checks, and
the disposable-session crash-test journal. Attach the journal with:

```sh
journalctl --user -b -u io.github.alexydaher.Salon.service > salon-session.log
```
