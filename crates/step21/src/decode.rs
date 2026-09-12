//! Small helpers for reading Part 21 argument text without a full parser.

/// Decode a Part 21 string literal body (between the quotes): `''` is a
/// quote, `\X2\HHHH...\X0\` is UTF-16BE hex, `\X\HH` is a Latin-1 byte.
///
/// # Examples
///
/// ```
/// use step21::decode::decode_string;
/// assert_eq!(decode_string(b"a''b"), "a'b");
/// assert_eq!(decode_string(b"\\X2\\00E9\\X0\\"), "\u{e9}");
/// assert_eq!(decode_string(b"\\X\\E9"), "\u{e9}");
/// ```
pub fn decode_string(raw: &[u8]) -> String {
    let mut out = String::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        let b = raw[i];
        if b == b'\'' && raw.get(i + 1) == Some(&b'\'') {
            out.push('\'');
            i += 2;
        } else if b == b'\\' && raw[i..].starts_with(b"\\X2\\") {
            let hex_start = i + 4;
            match find(&raw[hex_start..], b"\\X0\\") {
                Some(end) => {
                    let hex = &raw[hex_start..hex_start + end];
                    let units: Vec<u16> = hex
                        .as_chunks::<4>()
                        .0
                        .iter()
                        .filter_map(|c| u16::from_str_radix(std::str::from_utf8(c).ok()?, 16).ok())
                        .collect();
                    out.push_str(&String::from_utf16_lossy(&units));
                    i = hex_start + end + 4;
                }
                None => {
                    out.push('\\');
                    i += 1;
                }
            }
        } else if b == b'\\' && raw[i..].starts_with(b"\\X\\") && raw.len() >= i + 5 {
            match u8::from_str_radix(&String::from_utf8_lossy(&raw[i + 3..i + 5]), 16) {
                Ok(v) => {
                    out.push(v as char);
                    i += 5;
                }
                Err(_) => {
                    out.push('\\');
                    i += 1;
                }
            }
        } else {
            out.push(if b.is_ascii() { b as char } else { '\u{FFFD}' });
            i += 1;
        }
    }
    out
}

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    memchr::memmem::find(hay, needle)
}

/// The raw body of a string literal starting at `args[0] == b'\''`, plus the
/// offset just past its closing quote. `None` if `args` does not start with
/// a string.
pub fn leading_string(args: &[u8]) -> Option<(&[u8], usize)> {
    if args.first() != Some(&b'\'') {
        return None;
    }
    let mut p = 1;
    loop {
        let q = p + memchr::memchr(b'\'', &args[p..])?;
        if args.get(q + 1) == Some(&b'\'') {
            p = q + 2;
        } else {
            return Some((&args[1..q], q + 1));
        }
    }
}

/// Decoded first string argument, if the argument list starts with one.
pub fn first_string(args: &[u8]) -> Option<String> {
    leading_string(args).map(|(s, _)| decode_string(s))
}

/// Parse up to `max` numbers from `text`, where a number is a maximal run of
/// the characters `-+0-9.Ee` that parses as `f64` (runs that do not parse
/// are skipped).
pub fn numbers(text: &[u8], max: usize) -> Vec<f64> {
    let mut out = Vec::with_capacity(max);
    let mut i = 0;
    let is_num = |b: u8| b.is_ascii_digit() || matches!(b, b'-' | b'+' | b'.' | b'E' | b'e');
    while i < text.len() && out.len() < max {
        if is_num(text[i]) {
            let s = i;
            while i < text.len() && is_num(text[i]) {
                i += 1;
            }
            if let Ok(v) = std::str::from_utf8(&text[s..i])
                .unwrap_or("x")
                .parse::<f64>()
            {
                out.push(v);
            }
        } else {
            i += 1;
        }
    }
    out
}

/// First argument of an argument list, trimmed (used for enumerations such
/// as `.POSITIVE.`).
pub fn first_arg(args: &[u8]) -> &[u8] {
    let end = memchr::memchr(b',', args).unwrap_or(args.len());
    args[..end].trim_ascii()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_escapes() {
        assert_eq!(decode_string(b"a''b"), "a'b");
        assert_eq!(decode_string(b"\\X2\\672A4FDD5B58\\X0\\"), "未保存");
        assert_eq!(decode_string(b"\\X\\E9"), "é");
        assert_eq!(first_string(b"'x''y',#1"), Some("x'y".to_string()));
        assert_eq!(numbers(b"'',(1.,2.5E-1,-3.))", 3), vec![1.0, 0.25, -3.0]);
        assert_eq!(first_arg(b" .NEGATIVE. , #3"), b".NEGATIVE.");
    }
}
