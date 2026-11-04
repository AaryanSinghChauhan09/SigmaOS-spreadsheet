//! Format conversion and management
//! Follows: Open-Closed Principle, Strategy Pattern

use std::collections::HashMap;

/// Format converter
pub struct FormatConverter {
    converters: HashMap<String, Box<dyn FormatConversion>>,
}

trait FormatConversion {
    fn convert(&self, content: &str) -> Result<String, &'static str>;
}

impl FormatConverter {
    pub fn new() -> Self {
        FormatConverter {
            converters: HashMap::new(),
        }
    }

    pub fn register_converter(&mut self, from: String, to: String, converter: Box<dyn FormatConversion>) {
        let key = format!("{}->{}", from, to);
        self.converters.insert(key, converter);
    }

    pub fn convert(&self, content: &str, from: &str, to: &str) -> Result<String, &'static str> {
        let key = format!("{}->{}", from, to);
        if let Some(converter) = self.converters.get(&key) {
            converter.convert(content)
        } else {
            Err("Converter not found")
        }
    }
}

impl Default for FormatConverter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_converter_registry() {
        let mut converter = FormatConverter::new();
        assert!(converter.converters.is_empty());
    }
}
