from pathlib import Path


WORKFLOW = Path(".github/workflows/update-news.yml")


def test_snapshot_workflow_deploys_pages_without_writing_main():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "actions/upload-pages-artifact" in text
    assert "actions/deploy-pages" in text
    assert "pages: write" in text
    assert "id-token: write" in text
    assert "git push" not in text
    assert "contents: write" not in text


def test_snapshot_workflow_does_not_promote_demo_opml_to_production():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "follow.example.opml" not in text
    assert "FOLLOW_OPML_B64" in text


def test_snapshot_workflow_wires_optional_persona_enhancement():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "DEEPSEEK_API_KEY" in text
    assert "DEEPSEEK_PERSONA_ENABLED" in text
