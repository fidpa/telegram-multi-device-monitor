# Contributing to telegram-multi-device-monitor

Thank you for your interest in contributing!

## Code of Conduct

Be respectful. Keep discussions constructive and professional.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/fidpa/telegram-multi-device-monitor/issues)
2. Create a new issue with:
   - Clear title
   - Steps to reproduce
   - Expected vs actual behavior
   - System info: `uname -a && python3 --version`

### Suggesting Features

1. Check existing issues and discussions
2. Open an issue with the `enhancement` label
3. Describe the use case and expected behavior

### Pull Requests

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes following style guide
4. Run linters:
   ```bash
   black src/
   mypy --strict src/*.py
   shellcheck src/*.sh src/lib/*.sh
   yamllint config/
   ```
5. Submit PR with clear description

## Style Guide

### Python

- **Formatting**: Black (default settings)
- **Type Hints**: Required (Python 3.10+ style)
  ```python
  def process(data: dict[str, Any]) -> list[str] | None:
  ```
- **Docstrings**: Google-style
  ```python
  def function(arg: str) -> bool:
      """
      Brief description.

      Args:
          arg: Argument description

      Returns:
          Return value description
      """
  ```
- **Exit Codes**: Use `main() -> int` with `sys.exit(main())`

### Bash

- **Header**: Always start with `set -uo pipefail`
- **Linting**: `shellcheck -S warning`
- **Quoting**: Always quote variables: `"$var"` not `$var`
- **Functions**: Use lowercase with underscores
  ```bash
  my_function() {
      local arg="$1"
      # ...
  }
  ```

### YAML Configuration

- Use 2-space indentation
- Quote strings containing special characters
- Add comments for non-obvious values

## Commit Messages

Follow conventional commits format:

```
type: brief description

Optional longer description explaining the change.

- Bullet points for multiple changes
- Keep lines under 72 characters
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat: add SSH timeout configuration

- Add connect_timeout to ssh config
- Update documentation with examples
- Default: 10 seconds

fix: prevent sed injection in alert deduplication

Sanitize alert_id to only allow safe characters
before using in sed/grep patterns.
```

## Testing

Before submitting:

1. Test your changes locally
2. Run all linters (see above)
3. Test on target platform if possible (Linux, Raspberry Pi)

## Security

If you discover a security vulnerability, please:

1. **Do NOT** open a public issue
2. Use [GitHub Security Advisories](https://github.com/fidpa/telegram-multi-device-monitor/security/advisories/new)
3. See [SECURITY.md](SECURITY.md) for details

## Questions?

- Open a [Discussion](https://github.com/fidpa/telegram-multi-device-monitor/discussions)
- Check the [documentation](docs/)

Thank you for contributing!
