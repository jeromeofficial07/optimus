"""
Test the Phase 8B features SEPARATELY with temporary data (your real files are never touched).
    python -m tests.features_b_cli language     (also: workflows, analytics, all)
"""
import json
import sys
import tempfile
from pathlib import Path

from app.agent.events import ToolCallbacks
from app.agent.intent import IntentKind, recognize_intent
from app.agent.workflows import WORKFLOWS
from app.features import custom_workflows, multilingual
from app.features.analytics import AnalyticsCollector, AnalyticsFeature
from app.features.briefing import BriefingFeature
from app.features.custom_workflows import WorkflowFeature
from app.features.multilingual import LanguageFeature
from app.voice import languages
from app.voice.languages import LanguageState
from app.voice.multilingual import MultilingualSTT, MultilingualTTS
from tests import features_cli as base


def test_language(tmp):
    print("--- multilingual voice ---")
    check, L = base.check, languages
    check("Devanagari is detected as Hindi", L.detect_script_language("नमस्ते आप कैसे हैं") == "hi")
    check("Tamil script is detected", L.detect_script_language("வணக்கம் எப்படி இருக்கிறீர்கள்") == "ta")
    check("Latin text is not guessed", L.detect_script_language("hello how are you") is None)
    check("language names resolve", L.resolve_language("Spanish") == "es"
          and L.resolve_language("auto") == "auto" and L.resolve_language("klingon") is None)
    check("English needs no instruction", L.reply_instruction("en") == "" and "Hindi" in L.reply_instruction("hi"))
    check("an unknown voice is not installed", not L.voice_installed("xx"))
    tts = MultilingualTTS()
    tts.set_language("xx")
    check("an unknown language falls back to English", tts._language == "en")
    stt = MultilingualSTT()
    stt.unload()
    check("the speech model can be unloaded when idle", not stt.is_loaded)

    multilingual.LANG = LanguageState(persist=False)     # Never touch your real saved settings
    router, _, _ = base.make(tmp, LanguageFeature)
    multilingual.MULTILINGUAL_ENABLED = False
    check("when disabled it explains how to enable", "off" in base.ask(router, "switch language to hindi").lower())
    multilingual.MULTILINGUAL_ENABLED = True
    reply = base.ask(router, "reply in spanish")
    check("switching language", "Spanish" in reply and multilingual.LANG.preference == "es", reply[:70])
    check("an unknown language is refused", "don't know" in base.ask(router, "speak in klingon").lower())
    check("auto mode", "auto" in base.ask(router, "switch language to auto").lower()
          and multilingual.LANG.preference == "auto")
    check("the language list", "Hindi" in base.ask(router, "list languages"))
    multilingual.MULTILINGUAL_ENABLED = False


def test_workflows(tmp):
    print("--- custom workflow automation ---")
    check = base.check
    file = tmp / "workflows.json"
    custom_workflows.WORKFLOWS_FILE = file
    file.write_text(json.dumps({"workflows": [
        {"name": "test_flow", "triggers": ["run my test flow"],
         "steps": [{"tool": "daily_briefing"}, {"tool": "get_system_usage", "on_fail": "continue"}]},
        {"name": "bad_tool", "triggers": ["do something bad"], "steps": [{"tool": "format_disk"}]},
        {"name": "x", "triggers": ["short name"], "steps": [{"tool": "get_battery_status"}]},
        {"name": "system_check", "triggers": ["clash phrase"], "steps": [{"tool": "get_battery_status"}]},
    ]}))
    router, _, _ = base.make(tmp, BriefingFeature, WorkflowFeature)
    feature = router.features[1]
    try:
        check("a valid workflow is loaded", "test_flow" in WORKFLOWS)
        check("an unknown tool is rejected", "bad_tool" not in WORKFLOWS)
        check("a bad name is rejected", "x" not in WORKFLOWS)
        check("a built-in workflow cannot be replaced",
              not any("clash" in t for t in WORKFLOWS["system_check"].triggers))
        check("each problem is reported", len(feature.problems) == 3, str(len(feature.problems)))
        intent = recognize_intent("please run my test flow now")
        check("the trigger phrase is recognised", intent.kind is IntentKind.WORKFLOW and intent.workflow == "test_flow")
        controller = feature.s.controller
        report = controller.run_plan(controller.planner.from_workflow("test_flow"), ToolCallbacks())
        check("the workflow runs through the controller", report.succeeded and len(report.results) == 2)
        check("the list command", "test_flow" in base.ask(router, "list my workflows"))
        file.write_text("{ not json")
        base.ask(router, "reload workflows")
        check("invalid JSON is reported, not fatal", "test_flow" not in WORKFLOWS and bool(feature.problems))
    finally:
        for name in list(feature.loaded):
            WORKFLOWS.pop(name, None)


def test_analytics(tmp):
    print("--- system analytics ---")
    check = base.check
    collector = AnalyticsCollector()
    for _ in range(4):
        collector.sample()
    check("samples are collected", len(collector.recent()) == 4)
    stats = collector.stats(600)
    check("statistics are computed", bool(stats) and 0 <= stats["cpu_avg"] <= 100)
    check("top processes are listed", len(collector.top_processes(3)[1]) == 3)
    router, _, _ = base.make(tmp, AnalyticsFeature)
    seen = []
    router.features[0].s.ui = seen.append
    reply = base.ask(router, "system analytics")
    check("the report covers CPU and memory", "CPU" in reply and "Memory" in reply, reply.splitlines()[0])
    check("the dashboard command asks the GUI",
          "dashboard" in base.ask(router, "show the dashboard").lower() and seen == ["show_dashboard"])


def main():
    wanted = set(sys.argv[1:]) or {"all"}
    tests = {"language": test_language, "workflows": test_workflows, "analytics": test_analytics}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        for name, function in tests.items():
            if wanted & {name, "all"}:
                sub = Path(folder) / name
                sub.mkdir()
                function(sub)
                print()
    print(f"{base.passed} passed, {base.failed} failed.")


if __name__ == "__main__":
    main()