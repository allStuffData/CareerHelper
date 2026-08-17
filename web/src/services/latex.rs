/// LaTeX compilation service.
/// Runs pdflatex/xelatex as a subprocess and returns the PDF path.

use std::path::{Path, PathBuf};
use std::process::Command;

/// Compile a .tex file to PDF. Returns the path to the generated PDF.
pub fn compile(input: &Path) -> anyhow::Result<PathBuf> {
    let dir = input.parent().unwrap_or(Path::new("."));
    let filename = input.file_name()
        .and_then(|f| f.to_str())
        .ok_or_else(|| anyhow::anyhow!("Invalid filename"))?;

    // Two-pass compilation
    for _ in 0..2 {
        let output = Command::new("pdflatex")
            .args(["-interaction=nonstopmode", "-output-directory"])
            .arg(dir)
            .arg(filename)
            .current_dir(dir)
            .output()?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(anyhow::anyhow!("pdflatex failed: {}", stderr));
        }
    }

    let pdf = input.with_extension("pdf");
    if pdf.exists() {
        Ok(pdf)
    } else {
        Err(anyhow::anyhow!("PDF not found after compilation"))
    }
}
