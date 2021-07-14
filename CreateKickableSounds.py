#    Copyright (C) 2021  Adam Johnson
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from PyHSPlasma import *

parser = argparse.ArgumentParser()
parser.add_argument("input", type=Path, help="json instructions")
parser.add_argument("prp", type=Path, help="path to PRP file to work on")
parser.add_argument("--dry-run", action="store_true", help="just run the process, don't save any damage")

class CKSError(Exception):
    pass


def _load_instructions(input_path: Path) -> dict:
    logging.info("Loading instructions from JSON...")

    import json
    with input_path.open("r") as fp:
        return json.load(fp)

def _load_prp(path: Path, settings: Dict) -> Tuple[plResManager, plPageInfo]:
    logging.info("Loading registry...")

    mgr = plResManager()
    if path.is_file():
        if path.suffix.lower() != ".prp":
            raise CKSError(f"Unexpected file extension '{path.suffix}', expected '.prp'")
        page = mgr.ReadPage(path)
    else:
        path /= f"{settings['target']['age']}_District_{settings['target']['page']}.prp"
        if not path.is_file():
            raise CKSError(f"Input PRP not found: {path}")
        page = mgr.ReadPage(path)

    if page.age != settings["target"]["age"]:
        raise CKSError(f"Unexpected Age '{page.age}', expected '{settings['target']['age']}'")
    if page.page != settings["target"]["page"]:
        raise CKSError(f"Unexpected page '{page.page}', expected '{settings['target']['page']}'")
    return mgr, page

def _del_object(mgr: plResManager, key: plKey, indent: int = 3) -> None:
    logging.debug(f"{'  ' * indent}-> Nuking '{key}'")

    obj = key.object
    if isinstance(obj, plSceneObject):
        node = mgr.getSceneNode(key.location)
        node.delSceneObject(next(i for i, soKey in enumerate(node.sceneObjects) if soKey == key))

    mgr.DelObject(key)

def _nuke_objects(settings: dict, mgr: plResManager, loc: plLocation) -> None:
    logging.info("Nuking defunct objects...")

    for parentSO_name, parent_settings in settings["soundGroups"].items():
        if parentSO := next((i.object for i in mgr.getKeys(loc, plFactory.kSceneObject) if i.name == parentSO_name), None):
            logging.debug(f"  -> Checking '{parentSO_name}' emitters...")
            if not parentSO.coord:
                logging.debug("    -> No CoordinateInterface, bail!")
                continue
            parentCI: plCoordinateInterface = parentSO.coord.object
            for emitter in parent_settings["emitters"]:
                _nuke_emitter(mgr, parentCI, emitter["name"])

            if parentSO.sim:
                parentSI: plSimulationInterface = parentSO.sim.object
                parentPhys: plGenericPhysical = parentSI.physical.object
                if soundGroup_key := parentPhys.soundGroup:
                    _del_object(mgr, soundGroup_key, indent=2)
                    # Don't export a junked key, yo.
                    parentPhys.soundGroup = None

def _nuke_emitter(mgr: plResManager, parent: plCoordinateInterface, emitter_name: str) -> None:
    idx, emitterSO = next(((i, child.object) for i, child in enumerate(parent.children) if child.name == emitter_name), (None, None))
    if emitterSO is None:
        logging.debug(f"    -> Emitter {emitter_name} doesn't exist (yet)... Good.")
    else:
        logging.debug(f"    -> Nuking emitter '{emitter_name}'")
        parent.delChild(idx)
        _nuke_so_tree_recur(mgr, emitterSO)

def _nuke_so_tree_recur(mgr: plResManager, so: plSceneObject) -> None:
    # This should never happen. If it does, you will need a more powerful program.
    assert so.draw is None, "Cannot nuke a drawable object"
    assert so.sim is None, "Cannot nuke a physical object"
    assert not so.interfaces, "Cannot nuke an object with generic interfaces"

    # Terminate single modifiers only. If there are any stale multi modifiers... well, we'll
    # hit those up later.
    for i in (i for i in so.modifiers if isinstance(i.object, plSingleModifier)):
        _del_object(mgr, i)

    if audio_key := so.audio:
        audio: plAudioInterface = audio_key.object
        win_audible: plWinAudible = audio.audible.object
        for win_sound in win_audible.sounds:
            _del_object(mgr, win_sound)
        _del_object(mgr, audio.audible)
        _del_object(mgr, audio_key)

    if coord_key := so.coord:
        coord: plCoordinateInterface = coord_key.object
        for i in coord.children:
            _nuke_so_tree_recur(mgr, i.object)
        _del_object(mgr, coord_key)

    _del_object(mgr, so.key)

def _cleanup_multimods(mgr: plResManager, loc: plLocation) -> None:
    logging.info("Cleaning up stale MultiModifiers...")

    multimods = set((iKey for iType in mgr.getTypes(loc) for iKey in mgr.getKeys(loc, iType) if isinstance(iKey.object, plModifier)))
    for so in (i.object for i in mgr.getKeys(loc, plFactory.kSceneObject)):
        multimods -= set(so.modifiers)
    for i in multimods:
        _del_object(mgr, i, indent=1)

def _create_object(pClass: type, mgr: plResManager, target: plSceneObject, name: str, indent: int = 3) -> hsKeyedObject:
    logging.debug(f"{'  ' * indent}-> Creating [{pClass.__name__}] '{name}'")
    obj = pClass(name)
    mgr.AddObject(target.key.location, obj)
    if isinstance(obj, plSceneObject):
        mgr.getSceneNode(target.key.location).addSceneObject(obj.key)
    if isinstance(obj, plModifier):
        target.addModifier(obj.key)
    if isinstance(obj, plObjInterface):
        obj.owner = target.key
        LUT = {
            plAudioInterface: "audio",
            plCoordinateInterface: "coord",
            plFilterCoordInterface: "coord",
            plDrawInterface: "draw",
            plSimulationInterface: "sim",
        }
        if attr := LUT.get(pClass):
            setattr(target, attr, obj.key)
        else:
            target.addInterface(obj.key)
    if hasattr(obj, "sceneNode"):
        obj.sceneNode = mgr.getSceneNode(target.key.location).key
    return obj

def _create_emitters(settings: dict, mgr: plResManager, loc: plLocation) -> None:
    logging.info("Creating new emitters...")

    for parentSO_name, parent_settings in settings["soundGroups"].items():
        if parentSO := next((i.object for i in mgr.getKeys(loc, plFactory.kSceneObject) if i.name == parentSO_name), None):
            logging.debug(f"  -> Creating emitters for '{parentSO_name}'")
            parentCI: plCoordinateInterface = parentSO.coord.object
            for emitter in parent_settings["emitters"]:
                _create_emitter(mgr, parentSO, parentCI, emitter, parent_settings.get("type", "kNone"))

def _create_emitter(mgr: plResManager, parentSO: plSceneObject, parentCI: plCoordinateInterface, emitter: dict, surface: str) -> None:
    if emitter["type"] == "delete":
        logging.debug(f"    -> Skipping over stale emitter '{emitter['name']}'")
        return

    emitter_name = emitter['name']
    logging.debug(f"    -> Creating emitter '{emitter_name}'")
    emitterSO: plSceneObject = _create_object(plSceneObject, mgr, parentSO, emitter_name)
    emitterSO.synchFlags |= plSynchedObject.kExcludeAllPersistentState
    parentCI.addChild(emitterSO.key)
    emitterCI: plCoordinateInterface = _create_object(plCoordinateInterface, mgr, emitterSO, emitter_name)
    emitterCI.setProperty(plCoordinateInterface.kCanEverDelayTransform, True)
    emitterCI.setProperty(plCoordinateInterface.kDelayedTransformEval, True)

    # Bah, redundancy!
    emitter_name_no_sfx = emitter_name[3:] if emitter_name.lower().startswith("sfx") else emitter_name

    # Initialize all random sounds
    win_audible: plWinAudible = _create_object(plWinAudible, mgr, emitterSO, f"cSfx{emitter_name_no_sfx}")
    for i, soundBuf_name in enumerate(emitter["sounds"]):
        soundBuf_key = next((key for key in mgr.getKeys(parentSO.key.location, plFactory.kSoundBuffer) if key.name == soundBuf_name), None)
        if soundBuf_key is None:
            raise CKSError(f"SoundBuffer {soundBuf_name} could not be found!")

        win32_sound: plWin32Sound = _create_object(plWin32StaticSound, mgr, emitterSO, f"cSfx{emitter_name_no_sfx}_{i:02}")
        win32_sound.dataBuffer = soundBuf_key
        win32_sound.fadeInParams.currTime = -1.0
        win32_sound.fadeOutParams.currTime = -1.0

        # There should be no need to loop sliding sounds - the continued collision against a surface
        # should be sufficient to trigger new executions of the sliding sound.
        win32_sound.properties |= plSound.kPropIs3DSound | plSound.kPropIncidental

        # Optional settings
        soundSettingsLUT = {
            "currVolume": 0.0,
            "desiredVolume": 1.0,
            "innerCone": 360,
            "maxFalloff": 100,
            "minFalloff": 3,
            "outerCone": 360,
            "priority": 1,
        }
        settings = emitter.get("soundSettings", {})
        for key, value in soundSettingsLUT.items():
            setattr(win32_sound, key, settings.get(key, value))

        # EAX Settings are not in HSPlasma master as of the writing of this code.
        if eax := getattr(win32_sound, "eaxSettings", None):
            eaxSettingsLUT = {
                "room": 0,
                "roomHF": 0,
                "roomAuto": True,
                "roomHFAuto": True,
                "outsideVolHF": 0,
                "airAbsorptionFactor": 1.0,
                "roomRolloffFactor": 0.0,
                "dopplerFactor": 0.0,
                "rolloffFactor": 0.0,
                "occlusionSoftValue": 0.0,
            }
            settings = emitter.get("eaxSettings", {})
            if settings.get("enable"):
                # This does fun things under the hood, so special handling ahoy!
                eax.enable = True
                for key, value in eaxSettingsLUT.items():
                    setattr(eax, key, settings.get(key, value))

        # Whew!
        win_audible.addSound(win32_sound.key)

    emitterAI: plAudioInterface = _create_object(plAudioInterface, mgr, emitterSO, emitter_name)
    emitterAI.audible = win_audible.key

    randomSounds = _create_object(plRandomSoundMod, mgr, emitterSO, f"cSfxRand{emitter_name_no_sfx}")
    randomSounds.mode |= plRandomSoundMod.kNoRepeats | plRandomSoundMod.kOneCmd
    randomSounds.state = plRandomSoundMod.kStopped

    # Setup the PhysicalSnd group thingy...
    parentPhys: plGenericPhysical = parentSO.sim.object.physical.object
    if parentPhys.soundGroup is None or parentPhys.soundGroup.object is None:
        soundGroup: plPhysicalSndGroup = _create_object(plPhysicalSndGroup, mgr, parentSO, f"cSfxPhysSnd-{parentSO.key.name}")
        soundGroup.group = getattr(plPhysicalSndGroup, surface)
        parentPhys.soundGroup = soundGroup.key
    else:
        soundGroup: plPhysicalSndGroup = parentPhys.soundGroup.object

    if emitter["type"] in {"hit", "impact"}:
        sound_attr = "impactSounds"
    elif emitter["type"] in {"roll", "slide"}:
        sound_attr = "slideSounds"
    else:
        raise CKSError(f"Unexpected sound type '{emitter['type']}'")

    soundGroup_LUT = { i: value for i, value in enumerate(getattr(soundGroup, sound_attr)) }
    if emitter.get("surface", "all") == "all":
        for i in range(plPhysicalSndGroup.kUser3 + 1):
            soundGroup_LUT[i] = randomSounds.key
    else:
        soundGroup_LUT[getattr(plPhysicalSndGroup, emitter["surface"])] = randomSounds.key
    setattr(soundGroup, sound_attr, [soundGroup_LUT.get(i) for i in range(max(soundGroup_LUT.keys()) + 1)])

def _save_damage(path: Path, mgr: plResManager, page: plPageInfo) -> None:
    if path.is_dir():
        path /= page.getFilename(mgr.getVer())
    logging.info(f"Writing '{path}'...")
    mgr.WritePage(path, page)

def main(args):
    settings = _load_instructions(args.input)
    mgr, page = _load_prp(args.prp, settings)
    _nuke_objects(settings, mgr, page.location)
    _cleanup_multimods(mgr, page.location)
    _create_emitters(settings, mgr, page.location)
    if not args.dry_run:
        _save_damage(args.prp, mgr, page)

if __name__ == "__main__":
    import time

    start_time = time.perf_counter()
    try:
        args = parser.parse_args()
        plDebug.Init(plDebug.kDLNone)
        logging.basicConfig(format="[%(asctime)s] %(levelname)s: %(message)s", level=logging.DEBUG)
        logging.info("CreateKickableSounds __main__")
        main(args)
    except CKSError as e:
        logging.critical(str(e))
    finally:
        end_time = time.perf_counter()
        delta = end_time - start_time
        logging.info(f"CreateKickableSounds completed in {delta:.2f}s.")
