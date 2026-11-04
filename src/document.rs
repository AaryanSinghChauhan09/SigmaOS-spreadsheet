//! Document processing with advanced features
//! Follows: Abstraction, Encapsulation, Single Responsibility

use std::collections::HashMap;

/// Document format
#[derive(Debug, Clone, PartialEq)]
pub enum DocumentFormat {
    PlainText,
    Markdown,
    HTML,
    PDF,
    Word,
    Excel,
    PowerPoint,
}

/// Document metadata
#[derive(Debug, Clone)]
pub struct DocumentMetadata {
    pub title: String,
    pub author: String,
    pub created: u64,
    pub modified: u64,
    pub format: DocumentFormat,
}

/// Document
pub struct Document {
    pub metadata: DocumentMetadata,
    pub content: String,
    pub properties: HashMap<String, String>,
}

impl Document {
    pub fn new(title: String, content: String, format: DocumentFormat) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();
        
        Document {
            metadata: DocumentMetadata {
                title,
                author: "Unknown".to_string(),
                created: now,
                modified: now,
                format,
            },
            content,
            properties: HashMap::new(),
        }
    }

    pub fn set_property(&mut self, key: String, value: String) {
        self.properties.insert(key, value);
    }

    pub fn get_property(&self, key: &str) -> Option<&String> {
        self.properties.get(key)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_document_creation() {
        let doc = Document::new("Test".to_string(), "Content".to_string(), DocumentFormat::PlainText);
        assert_eq!(doc.metadata.title, "Test");
    }
}
