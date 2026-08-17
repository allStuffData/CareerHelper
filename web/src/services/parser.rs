//! Document parsing service.
//! Extracts structured text from PDF, DOCX, Markdown, and HTML files.
//! Phase 1 integration — currently a stub with types defined.

/// Supported document formats.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)]
pub enum DocumentFormat {
    Pdf,
    Docx,
    Markdown,
    Html,
    Txt,
}

#[allow(dead_code)]
impl DocumentFormat {
    pub fn from_extension(path: &std::path::Path) -> Option<Self> {
        match path.extension()?.to_str()?.to_lowercase().as_str() {
            "pdf" => Some(Self::Pdf),
            "docx" => Some(Self::Docx),
            "md" => Some(Self::Markdown),
            "html" | "htm" => Some(Self::Html),
            "txt" => Some(Self::Txt),
            _ => None,
        }
    }
}

/// Parsed document content.
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct ParsedDocument {
    pub raw_text: String,
    pub format: DocumentFormat,
}

/// Parse a document from a file path.
#[allow(dead_code)]
pub fn parse(path: &std::path::Path) -> anyhow::Result<ParsedDocument> {
    let format = DocumentFormat::from_extension(path)
        .ok_or_else(|| anyhow::anyhow!("Unsupported file format: {:?}", path.extension()))?;

    match format {
        DocumentFormat::Txt | DocumentFormat::Markdown | DocumentFormat::Html => {
            let text = std::fs::read_to_string(path)?;
            Ok(ParsedDocument { raw_text: text, format })
        }
        DocumentFormat::Pdf | DocumentFormat::Docx => {
            let output = std::process::Command::new("pandoc")
                .arg(path).arg("-t").arg("plain").arg("--wrap=none")
                .output()
                .map_err(|e| anyhow::anyhow!(
                    "pandoc not found. Install pandoc to parse PDF/DOCX files: {}", e
                ))?;
            if !output.status.success() {
                let stderr = String::from_utf8_lossy(&output.stderr);
                return Err(anyhow::anyhow!("pandoc failed: {}", stderr));
            }
            let text = String::from_utf8_lossy(&output.stdout).to_string();
            Ok(ParsedDocument { raw_text: text, format })
        }
    }
}
