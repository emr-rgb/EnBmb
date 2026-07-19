#!/usr/bin/env python3
"""
Apply Zim's reference sound configuration to EnB sounds.ini.
Mutes UI/narration/footstep sounds, lowers global defaults,
normalizes weapon/combat sounds to ~0.4 baseline.
Safe to run multiple times. Creates sounds.ini.bak on first run.
"""

import re
import os
import shutil
import sys

if sys.platform == "win32":
    from enb_path import get_enb_install_path
    SOUNDS_INI = os.path.join(get_enb_install_path(), "Data", "client", "ini", "sounds.ini")
else:
    SOUNDS_INI = os.path.expanduser(
        "~/.wine-enb/drive_c/Program Files/EA GAMES/Earth & Beyond/"
        "Data/client/ini/sounds.ini"
    )

# Global key (lowercase) → target value  (before first section header)
GLOBAL_CHANGES = {
    "default_volume":        "0.1",
    "default_dialog_volume": "0.0000",
}

# Sections that also need SoundPriority zeroed
ZERO_PRIORITY_SECTIONS = {
    "click1.wav", "click1b.wav",
    "login_hand_glow", "login_hand_slide_in",
    "login_hand_slide_out", "login_mouse_click",
}

# Section name (lowercase) → target SoundVolume string
SECTION_VOLUMES = {
    # Avatar / login screen
    "avatar_delete_character":    "0.9000",  # patch raises this one
    "avatar_highlight":           "0.0000",
    "login_hand_glow":            "0.0000",
    "login_hand_slide_in":        "0.0000",
    "login_hand_slide_out":       "0.0000",
    "login_mouse_click":          "0.0000",
    "login_mouse_over_buttons":   "0.0000",
    "testmulti":                  "0.0000",
    # UI / login sounds
    "planet_spin.wav":            "0.0000",  # rotating planet in character creator
    "whoosh1b.wav":               "0.0000",
    "fe_music.mp3":               "0.0000",
    "click1.wav":                 "0.0000",
    "click1b.wav":                "0.0000",
    "click1c.wav":                "0.0000",
    "newopt1.wav":                "0.0000",
    "electro1.wav":               "0.0000",
    "targety1.wav":               "0.0000",
    "interface_menuslide01c.wav": "0.0000",
    "fontcricket.wav":            "0.0000",
    "fontclick.wav":              "0.0000",
    "fontshoosh.wav":             "0.0000",
    "inc_dec01.wav":              "0.0000",
    "sr_electronicblip01.wav":    "0.0000",
    "sr_electronicblip12.wav":    "0.0000",
    "sr_electronicblip13.wav":    "0.0000",
    "sr_electronicblip15.wav":    "0.0000",
    "sr_electronicblip18.wav":    "0.0000",
    "sr_scifielectronic40.wav":   "0.0000",
    "sr_scifielectronic42.wav":   "0.0000",
    "textclick01.wav":            "0.0000",
    "textclick02.wav":            "0.0000",
    "textclick03.wav":            "0.0000",
    "sr_generalclick03.wav":      "0.0000",
    "sr_generalclick04.wav":      "0.0000",
    "sr_ziprollover02.wav":       "0.0000",
    "roll_select02b.wav":         "0.0000",
    "sr_generalclick17b.wav":     "0.0000",
    "sr_generalclick22b.wav":     "0.0000",
    "textclick09a.wav":           "0.0000",
    "sr_digitalcricketsd.wav":    "0.0000",
    "sr_digitalcricketsb.wav":    "0.0000",
    "buttonclick01.wav":          "0.0000",
    "buttonclick02.wav":          "0.0000",
    "sn_scifi_beep_6.wav":        "0.0000",
    "sn_scifi_text_click_2.wav":  "0.0000",
    "sr_rollover14b.wav":         "0.0000",
    "slider_bar_1.wav":           "0.0000",
    "message_1.wav":              "0.0000",
    "snbeep14.wav":               "0.0000",
    "text_warning":               "0.0000",
    "text_error":                 "0.0000",
    # Megan voice / foley (character creator screen)
    "narrator_name_megan.wav":    "0.0000",
    "megan_ips.wav":              "0.0000",
    "megan_psi.wav":              "0.0000",
    "megan_wlc.wav":              "0.0000",
    "megan_knock_glass":          "0.0000",
    "megan_foot_step_glass":      "0.0000",
    "sfx_megan_button_1":         "0.0000",
    "sfx_megan_button_2":         "0.0000",
    "sfx_megan_button_3":         "0.0000",
    # Character foley
    "sfx_cloth_foley_1":          "0.0000",
    "sfx_cloth_foley_2":          "0.0000",
    "sfx_foley_clap_1":           "0.0000",
    "sfx_hand_foley_1":           "0.0000",
    "sfx_run_for_cover":          "0.0000",
    # Haywire
    "haywire idle":               "0.0000",
    "haywire start":              "0.0000",
    # NPC ambient
    "sfx_vrix_idle_growls":       "0.2600",
    # Shield recharge
    "recharge_shield_untuned_on.wav":    "0.0000",
    "recharge_shield_untuned_idle.wav":  "0.0000",
    "recharge_shield_untuned_off.wav":   "0.0000",
    "shield_recharge_beam_01.wav":       "0.0000",
    "test.wav":                          "0.0000",
    # Psionic shield
    "sfx_pre_delay_psionic":             "0.0000",
    "sfx_wait_state_psionic":            "0.0000",
    "sfx_pre_delay_psionic_mod":         "0.0000",
    "sfx_wait_state_psionic_mod":        "0.0000",
    "psionic_shield_idle.wav":           "0.0000",
    "psionic_shield_phase_on.wav":       "0.0000",
    "psionic_shield_delivery.wav":       "0.0000",
    "psionic_shield_idle_red":           "0.0000",
    "psionic_shield_phase_on_red":       "0.0000",
    "psionic_shield_delivery_red":       "0.0000",
    "psionic_tune.wav":                  "0.0000",
    # Environmental shield
    "sfx_pre_delay_environment":         "0.0000",
    "sfx_wait_state_environment":        "0.0000",
    "sfx_pre_delay_environment_mod":     "0.0000",
    "sfx_wait_state_environment_mod":    "0.0000",
    "enviromental_shield_idle.wav":      "0.0000",
    "enviromental_shield_phase_on.wav":  "0.0000",
    "enviromental_shield_phase_off.wav": "0.0000",
    # Teleport
    "sfx_new_teleport_01a.wav":          "0.0000",
    "sfx_new_teleport_04a.wav":          "0.0000",
    # Afterburn / ambience
    "afterburn.wav":                     "0.0000",
    "ext_planet_ambi_1.wav":             "0.0000",
    "station_ambi_22.wav":               "0.0000",
    "station_ambi_21.wav":               "0.0000",
    # Reduce (not zero)
    "ambience_spacestation01a.wav":             "0.1000",
    "hologram01.wav":                           "0.0100",
    # Cloaking
    "cloaking_loop_1.wav":                      "0.4000",
    "cloak_phase_1.wav":                        "0.4000",
    "cloaking_flash.wav":                       "0.4000",
    "stealth_loop_1.wav":                       "0.4000",
    "stealth_flash.wav":                        "0.4000",
    # Shield inversion
    "shield_inversion_grow.wav":                "0.1000",
    "shield_inversion_shield.wav":              "0.1000",
    "shield_inversion_energy_beam.wav":         "0.1000",
    # Hacking
    "hacking_beam_level_1.wav":                 "0.6000",
    "hacking_beam_level_5.wav":                 "0.6000",
    "hacking_level_3_pass_effect_part_1.wav":   "0.6000",
    # Mining / prospecting
    "mining_dep_attack.wav":                    "0.4000",
    "rev_prospect_beam.wav":                    "0.4000",
    # Crafting
    "analyze_1.wav":                            "0.2000",
    "analyze1.wav":                             "0.2000",
    "manufacture_1.wav":                        "0.2000",
    "failure_1.wav":                            "0.2000",
    # Boss
    "enrage_level_1_beam.wav":                  "0.3400",
    # Weapons
    "laser10.wav":                              "0.4000",
    "laser12.wav":                              "0.4000",
    "laser9.wav":                               "0.4000",
    "energy_bolt02.wav":                        "0.4000",
    "energy_bolt01.wav":                        "0.4000",
    "energy_beam2.wav":                         "0.4000",
    "energy_partical_bolt.wav":                 "0.4800",
    "energy_x_bolt.wav":                        "0.4000",
    "energy_clip_bolt.wav":                     "0.4800",
    "energy_lance_projectile.wav":              "0.4000",
    "explosive_charge.wav":                     "0.4000",
    "explosive_charge_b.wav":                   "0.4000",
    "explosive_simple.wav":                     "0.4000",
    "explosive_saber.wav":                      "0.4000",
    "explosive_missile_b.wav":                  "0.4000",
    "explosive_missile_2.wav":                  "0.4600",
    "explosive_missile_3.wav":                  "0.4600",
    "explo_slicing_missile.wav":                "0.4000",
    "nota_laser_1_b.wav":                       "0.4000",
    "nota_laser_2_b.wav":                       "0.4000",
    "nota_laser_3.wav":                         "0.4000",
    "nota_laser_4.wav":                         "0.4000",
    "nota_laser_5.wav":                         "0.4000",
    "nota_laser_6.wav":                         "0.4000",
    "nota_laser_7_b.wav":                       "0.4000",
    "nota_laser_8_b.wav":                       "0.4000",
    "nota_laser_9_b.wav":                       "0.4000",
    "nota_laser_10_b.wav":                      "0.4000",
    "nota_laser_11_b.wav":                      "0.4000",
    "nota_laser_13_c.wav":                      "0.4000",
    "nota_laser_14_b.wav":                      "0.4400",
    "nota_laser_15.wav":                        "0.4400",
    "nota_laser_16_b.wav":                      "0.4600",
    "synth_laser_1_b.wav":                      "0.4000",
    "synth_laser_2.wav":                        "0.4000",
    "synth_laser_3_d.wav":                      "0.4000",
    "synth_laser_4_b.wav":                      "0.4000",
    "synth_laser_5.wav":                        "0.4000",
    "synth_laser_6_b.wav":                      "0.4000",
    "synth_laser_7_b.wav":                      "0.4000",
    "synth_laser_8_b.wav":                      "0.4000",
    "synth_laser_9_b.wav":                      "0.4000",
    "synth_laser_10.wav":                       "0.4800",
    "synth_laser_11.wav":                       "0.4800",
    "sfx_new_laser_1_b.wav":                    "0.4000",
    "sfx_new_laser_6.wav":                      "0.4000",
    "laser_7.wav":                              "0.4000",
    "laserbl.wav":                              "0.4200",
    "lasergr.wav":                              "0.4000",
    "plasma_torpedo.wav":                       "0.4000",
    "plasma_ball.wav":                          "0.4000",
    "massive_energy_beam_d.wav":                "0.4600",
    "emp_lightning_02.wav":                     "0.4000",
    "emp_missile.wav":                          "0.4000",
    "emp_missile_2.wav":                        "0.4000",
    "chem_missile.wav":                         "0.4000",
    "impact_bolt.wav":                          "0.4000",
    "impact_simple.wav":                        "0.4000",
    "impact_razor_b.wav":                       "0.4000",
    "impact_exotic.wav":                        "0.4000",
    "projectiletracer_b.wav":                   "0.4800",
    "projectiletracer_b_double.wav":            "0.4200",
    "projectilelightwave.wav":                  "0.4000",
    "projectileexotic.wav":                     "0.4000",
    "sfx_blue_railgun_1_b.wav":                 "0.4200",
    "sfx_green_photon_torpedo_1_b.wav":         "0.4400",
    "sfx_orange_photon_1.wav":                  "0.4400",
    "sfx_blue_photon_1.wav":                    "0.4400",
}


def section_target(name: str):
    lo = name.lower().strip()
    if lo in SECTION_VOLUMES:
        return SECTION_VOLUMES[lo]
    if lo.startswith("narrator_"):
        return "0.0000"
    if lo.startswith("1492_"):
        return "0.0000"
    if lo in ("run1.wav", "run2.wav", "walk1.wav"):
        return "0.0000"
    if lo.startswith("megan_"):
        return "0.0000"
    if lo.startswith("foot_step_"):
        return "0.0000"
    if lo in ("sfx_foot_scuff_1", "sfx_foley_foot_metal"):
        return "0.0000"
    return None


def apply(path: str) -> int:
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"Backup created: {bak}")

    with open(path, encoding="latin-1") as f:
        lines = f.readlines()

    section = None      # None = global header area
    target_vol = None
    zero_prio = False
    changed = 0
    out = []

    for line in lines:
        hdr = re.match(r"^\[([^\]]+)\]", line)
        if hdr:
            section = hdr.group(1).strip()
            target_vol = section_target(section)
            zero_prio = section.lower().strip() in ZERO_PRIORITY_SECTIONS
            out.append(line)
            continue

        # Global area or SOUND_DEFAULTS section (Default_Dialog_Volume lives there)
        if section is None or section.lower() == "sound_defaults":
            km = re.match(r"^(\w+)\s*=", line)
            if km and km.group(1).lower() in GLOBAL_CHANGES:
                new_val = GLOBAL_CHANGES[km.group(1).lower()]
                new_line = re.sub(
                    r"(" + re.escape(km.group(1)) + r"\s*=)\s*[\d.]+",
                    r"\g<1>" + new_val,
                    line,
                    flags=re.IGNORECASE,
                )
                if new_line != line:
                    changed += 1
                out.append(new_line)
                continue
            out.append(line)
            continue

        # SoundVolume in a targeted section
        if target_vol is not None and re.match(r"^SoundVolume\s*=", line, re.IGNORECASE):
            new_line = re.sub(
                r"(SoundVolume\s*=)\s*[\d.]+",
                r"\g<1>" + target_vol,
                line,
                flags=re.IGNORECASE,
            )
            if new_line != line:
                changed += 1
            out.append(new_line)
            continue

        # SoundPriority in special sections
        if zero_prio and re.match(r"^SoundPriority\s*=", line, re.IGNORECASE):
            new_line = re.sub(
                r"(SoundPriority\s*=)\s*[\d.]+",
                r"\g<1>0.000000",
                line,
                flags=re.IGNORECASE,
            )
            if new_line != line:
                changed += 1
            out.append(new_line)
            continue

        out.append(line)

    with open(path, "w", encoding="latin-1") as f:
        f.writelines(out)

    return changed


if __name__ == "__main__":
    if not os.path.exists(SOUNDS_INI):
        print(f"ERROR: sounds.ini not found at:\n  {SOUNDS_INI}", file=sys.stderr)
        sys.exit(1)
    n = apply(SOUNDS_INI)
    print(f"Done — {n} change(s) applied to {os.path.basename(SOUNDS_INI)}")
