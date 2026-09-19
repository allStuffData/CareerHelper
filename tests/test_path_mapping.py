"""Artifact download containment for the reorganized resources/ layout.

Phase 1 stores the compiled PDF under ``resources/output`` and the working
``.tex`` under ``resources/workspace``. The FastAPI download endpoints must
serve those real artifacts instead of returning 403, while still rejecting
paths outside the allowed roots.
"""

from __future__ import annotations

from app.models.generation import Generation, GenerationStage, GenerationStatus


def _completed_generation(generation_id: str, **paths) -> Generation:
    return Generation(
        id=generation_id,
        company="Acme",
        role="PM",
        job_description="Lead programs.",
        status=GenerationStatus.COMPLETED,
        stage=GenerationStage.COMPLETED,
        **paths,
    )


def test_allowed_roots_include_phase1_output_and_workspace(settings):
    roots = settings.allowed_artifact_roots
    assert settings.phase1_output_dir.resolve() in roots
    assert settings.phase1_workspace_dir.resolve() in roots
    assert settings.resources_dir.resolve() in roots


def test_download_serves_pdf_under_resources_output(settings, store, client):
    output_dir = settings.phase1_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf = output_dir / "GopalKumar_Acme_PM_20260102.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% real artifact\n")

    store.create_generation(_completed_generation("real-pdf", pdf_path=str(pdf)))

    response = client.get("/api/generations/real-pdf/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "GopalKumar_Acme_PM_20260102.pdf" in response.headers[
        "content-disposition"
    ]


def test_download_serves_tex_under_resources_workspace(settings, store, client):
    workspace = settings.phase1_workspace_dir
    workspace.mkdir(parents=True, exist_ok=True)
    tex = workspace / "GopalKumar_Resume.tex"
    tex.write_text("\\documentclass{article}\n\\begin{document}x\\end{document}")

    store.create_generation(_completed_generation("real-tex", tex_path=str(tex)))

    response = client.get("/api/generations/real-tex/tex")
    assert response.status_code == 200
    assert "documentclass" in response.text


def test_download_rejects_artifact_outside_allowed_roots(
    settings, store, client, tmp_path
):
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF-1.4\n% not allowed\n")

    store.create_generation(
        _completed_generation("outside", pdf_path=str(outside))
    )

    response = client.get("/api/generations/outside/pdf")
    assert response.status_code == 403
