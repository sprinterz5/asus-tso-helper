"""System facts and settings: model, CPU, services, sensors, sleep mode."""
import os
import shutil

from .common import _hwmon, _read, _read_int, run


MEM_SLEEP = "/sys/power/mem_sleep"


def deep_sleep():
    """True / False: the laptop sleeps in S3 ("deep") / in s2idle; None when the firmware has
    only one of them (most laptops since 2020 have no S3, there is nothing to choose)."""
    try:
        with open(MEM_SLEEP) as f:
            modes = f.read().split()
    except OSError:
        return None
    if "deep" not in " ".join(modes) or "s2idle" not in " ".join(modes):
        return None
    return "[deep]" in modes


def set_deep_sleep(on):
    """Now and after every boot (mem_sleep_default on the kernel command line), one password."""
    mode = "deep" if on else "s2idle"
    if shutil.which("grubby"):
        boot = (f"grubby --update-kernel=ALL --args=mem_sleep_default=deep" if on
                else "grubby --update-kernel=ALL --remove-args=mem_sleep_default")
    elif shutil.which("update-grub"):  # Debian, Ubuntu
        conf = "/etc/default/grub.d/asus-tso-helper-sleep.cfg"
        boot = (f"mkdir -p /etc/default/grub.d && echo 'GRUB_CMDLINE_LINUX_DEFAULT=\"$GRUB_CMDLINE_LINUX_DEFAULT "
                f"mem_sleep_default=deep\"' > {conf} && update-grub" if on else f"rm -f {conf} && update-grub")
    else:
        boot = "true"  # unknown boot loader: for this boot only
    return run("pkexec", "sh", "-c", f"echo {mode} > {MEM_SLEEP} && {boot}", timeout=120)


def cpu_name():
    for line in (_read("/proc/cpuinfo", "") or "").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].replace("with Radeon Graphics", "").strip()
    return ""


def services_running():
    names = ("asusd", "cardwired")
    return [n for n in names if run("systemctl", "is-active", "--quiet", n, timeout=5)[0]]


def model_name():
    """'ASUS TUF Gaming A15 FA507NV_FA507NV' -> 'ASUS TUF Gaming A15 FA507NV'."""
    name = _read("/sys/class/dmi/id/product_name", "")
    return name.split("_")[0].strip()


def sensors(include_dgpu):
    """Cheap sysfs reads, plus nvidia-smi when include_dgpu. Each nvidia-smi run keeps the dGPU
    awake for a few seconds more, so the caller asks rarely (ui.DGPU_TEMP_EVERY)."""
    out = {"cpu": None, "igpu": None, "dgpu": None, "fans": {}}
    k10 = _hwmon("k10temp") or _hwmon("coretemp")
    if k10:
        t = _read_int(os.path.join(k10, "temp1_input"))
        out["cpu"] = t / 1000 if t is not None else None
    amdgpu = _hwmon("amdgpu")
    if amdgpu:
        t = _read_int(os.path.join(amdgpu, "temp1_input"))
        out["igpu"] = t / 1000 if t is not None else None
    asus = _hwmon("asus")
    if asus:
        for n in (1, 2, 3):
            rpm = _read_int(os.path.join(asus, f"fan{n}_input"))
            if rpm is not None:
                label = _read(os.path.join(asus, f"fan{n}_label"), f"fan{n}")
                out["fans"][label.replace("_fan", "")] = rpm
    if include_dgpu:
        ok, val = run("nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits",
                      timeout=3)
        if ok and val.strip().isdigit():
            out["dgpu"] = int(val.strip())
    return out
