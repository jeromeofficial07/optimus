"""
Test each Phase 8 feature SEPARATELY with temporary data.
Run from the project root:
    python -m tests.features_cli files       (also: briefing, history, coding, web, weblive, all)
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.agent.agent import Agent
from app.agent.events import ToolCallbacks
from app.agent.executor import ToolExecutor
from app.agent.path_guard import PathGuard
from app.agent.registry import ToolContext
from app.features.base import Services
from app.features.briefing import BriefingFeature, build_briefing
from app.features.coding import CodingFeature
from app.features.file_search import FileSearchFeature
from app.features.history import HistoryFeature
from app.features.router import FeatureRouter
from app.storage.repositories import Storage
from app.tools.builtin import build_default_registry
from app.tools.productivity import register_productivity_tools

passed = failed = 0
CB = ToolCallbacks(confirm=lambda request: False)


class FakeLLM:
    """Stands in for the AI: it simply returns the prompt, so tests can inspect it."""
    def stream_with_system(self, system, user):
        yield user


def check(label, condition, detail=""):
    global passed, failed
    passed += bool(condition)
    failed += not condition
    print(f"[{'PASS' if condition else 'FAIL'}] {label}" + (f"   -> {detail}" if detail else ""))


def make(tmp: Path, *feature_classes):
    docs = tmp / "docs"
    docs.mkdir(exist_ok=True)
    storage = Storage(tmp / "test.db")
    context = ToolContext(guard=PathGuard([docs]))
    executor = ToolExecutor(build_default_registry(), context)
    register_productivity_tools(executor.registry, storage)
    services = Services(storage, executor.registry, Agent(executor).controller, context, llm=FakeLLM())
    features = [cls(services) for cls in feature_classes]
    for feature in features:
        feature.register_tools()
    return FeatureRouter(features), storage, docs


def ask(router, text) -> str:
    reply = router.handle(text, CB)
    return "(not handled)" if reply is None else reply if isinstance(reply, str) else "".join(reply)


def test_files(tmp):
    print("--- natural language file search ---")
    router, _, docs = make(tmp, FileSearchFeature)

    def make_file(name, days_ago=0, size=10, hour=None):
        path = docs / name
        path.write_bytes(b"x" * size)
        when = datetime.now() - timedelta(days=days_ago)
        if hour is not None:
            when = when.replace(hour=hour, minute=0)
        os.utime(path, (when.timestamp(), when.timestamp()))

    make_file("Marketing_Plan_Q3.pdf", days_ago=3)
    make_file("marketing_notes.txt", days_ago=20)
    make_file("budget.xlsx", days_ago=1, hour=12)
    make_file("photo.jpg")
    make_file("big_video.mp4", size=2 * 1024 * 1024)

    reply = ask(router, "find the marketing pdf")
    check("name + type", "Marketing_Plan_Q3.pdf" in reply and "marketing_notes.txt" not in reply)
    check("type + yesterday", "budget.xlsx" in ask(router, "find spreadsheets from yesterday"))
    reply = ask(router, "show me files modified in the last 7 days")
    check("last 7 days", "Marketing_Plan_Q3.pdf" in reply and "marketing_notes.txt" not in reply)
    check("size filter", "big_video.mp4" in ask(router, "find files bigger than 1 mb"))
    check("images", "photo.jpg" in ask(router, "find images"))
    check("no match says so", "No files found" in ask(router, "find the quarterly report file"))
    check("non-file question is ignored", router.handle("find out who won the match", CB) is None)


def test_briefing(tmp):
    print("--- daily briefing ---")
    router, storage, _ = make(tmp, BriefingFeature)
    storage.memory.remember("name", "Jerome", "profile")
    storage.tasks.add("Buy milk", datetime.now() - timedelta(days=1))
    storage.tasks.add("Send report", datetime.now().replace(hour=23, minute=0))
    storage.tasks.add("Learn Piper")
    storage.reminders.add("Call mom", datetime.now() + timedelta(minutes=30))
    reply = ask(router, "good morning")
    check("greets by name", "Jerome" in reply)
    check("overdue task", "Overdue" in reply and "Buy milk" in reply)
    check("due today", "Due today" in reply and "Send report" in reply)
    check("undated tasks counted", "more open task" in reply)
    check("reminder listed", "Call mom" in reply or "none" in reply, "reminder may fall on another day near midnight")
    check("'daily briefing' also works", "Daily briefing for" in ask(router, "daily briefing"))
    print(build_briefing(storage))


def test_history(tmp):
    print("--- contextual memory retrieval (full-text search) ---")
    router, storage, _ = make(tmp, HistoryFeature)
    index = router.features[0].index
    if not index.available:
        print("[SKIP] this Python build has no FTS5 support")
        return
    first = storage.conversations.create("Flask deployment")
    storage.messages.add(first, "user", "How do I deploy a Flask app with gunicorn?")
    storage.messages.add(first, "assistant", "Use gunicorn behind nginx and set environment variables.")
    second = storage.conversations.create("Cooking")
    storage.messages.add(second, "user", "What is a good pasta recipe?")
    reply = ask(router, "what did we talk about regarding flask")
    check("finds the right conversation", "gunicorn" in reply and "pasta" not in reply)
    check("'search my history for' works", "gunicorn" in ask(router, "search my history for deployment"))
    check("excluding the current chat", index.search("flask gunicorn", exclude_id=first) == [])
    check("context only when the past is mentioned",
          index.context_for("last time we discussed flask deployment") and not index.context_for("tell me about flask"))
    storage.conversations.delete(first)
    check("deleting a conversation removes it from the index", index.search("gunicorn") == [])


def test_coding(tmp):
    print("--- coding assistant ---")
    router, _, docs = make(tmp, CodingFeature)
    (docs / "sample.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    reply = ask(router, "explain sample.py")
    check("reads the file and builds the prompt", "def hello" in reply and "Explain what this file" in reply)
    check("review uses a different task", "Review this code" in ask(router, "review sample.py"))
    check("path outside allowed folders is refused", "outside" in ask(router, r"explain C:\Windows\win.ini").lower())
    check("write request", "function" in ask(router, "write a python function that reverses a string"))
    check("error explanation", "KeyError" in ask(router, "explain this error: KeyError 'name'"))
    check("normal chat is ignored", router.handle("how are you today", CB) is None)


def test_web():
    print("--- web search (offline checks) ---")
    from app.features import web
    for label, url, expected in [
        ("localhost blocked", "http://localhost/", False), ("127.0.0.1 blocked", "http://127.0.0.1:8000/", False),
        ("home network blocked", "http://192.168.1.1/", False), ("file:// blocked", "file:///C:/Windows/win.ini", False),
        ("credentials in URL blocked", "https://user:pw@8.8.8.8/", False), ("odd port blocked", "https://8.8.8.8:8080/", False),
        ("public address allowed", "https://8.8.8.8/", True)]:
        check(label, web.is_public_url(url) is expected)
    title, text = web.html_to_text(
        "<html><title>T</title><nav>Menu links</nav><script>var x=1;</script>"
        "<p>This is a real paragraph with enough words to be kept in the extracted text.</p></html>", 500)
    check("page text extraction", title == "T" and "real paragraph" in text and "var x" not in text and "Menu" not in text)
    sample = ('<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa&rut=1">One</a>'
              '<a class="result__snippet">First snippet</a></div>'
              '<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fb">Two</a></div>')
    results = web.parse_ddg(sample)
    check("search result parsing", [r.url for r in results] == ["https://example.org/a", "https://example.org/b"])
    check("snippets stay with the right result", results[0].snippet == "First snippet" and results[1].snippet == "")


def test_weblive():
    print("--- web search (LIVE, needs internet) ---")
    from app.features import web
    try:
        results = web.search_web("python programming language")
        check("search returns results", len(results) > 0, f"{len(results)} results; first: {results[0].title}")
        title, text = web.html_to_text(web.http_get(results[0].url), 1500)
        check("a result page can be read", len(text) > 100, f"{title!r}, {len(text)} characters")
    except Exception as exc:
        print(f"[SKIP] no internet or the search service blocked the request: {exc}")


def main():
    wanted = set(sys.argv[1:]) or {"all"}
    tests = {"files": test_files, "briefing": test_briefing, "history": test_history, "coding": test_coding}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        for name, function in tests.items():
            if wanted & {name, "all"}:
                sub = Path(folder) / name
                sub.mkdir()
                function(sub)
                print()
    if wanted & {"web", "all"}:
        test_web()
    if "weblive" in wanted:
        test_weblive()
    print(f"\n{passed} passed, {failed} failed.")


if __name__ == "__main__":
    main()