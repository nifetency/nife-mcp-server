# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

### How to Report

If you discover a security vulnerability, please send an email to:

📧 **security@nife.io**

Please include the following information:

- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

1. **Acknowledgment** - We'll acknowledge receipt within 24 hours
2. **Investigation** - We'll investigate and validate the issue
3. **Updates** - We'll keep you informed of our progress
4. **Resolution** - We'll work on a fix and coordinate disclosure
5. **Credit** - We'll credit you in the security advisory (unless you prefer to remain anonymous)

### Disclosure Policy

- We'll work with you to understand the scope of the vulnerability
- We'll aim to release a fix within 90 days
- We'll credit researchers who responsibly disclose vulnerabilities
- We'll publicly disclose after a fix is released

## Security Best Practices

### For Users

1. **Keep Updated**
   ```bash
   pip install --upgrade nife-mcp-server
   ```

2. **Secure Your Token**
   - Never commit tokens to version control
   - Use environment variables
   - Rotate tokens regularly

3. **Use HTTPS**
   - Always use secure connections
   - Verify SSL certificates

4. **Limit Permissions**
   - Use least-privilege access tokens
   - Restrict token scopes

### For Developers

1. **Dependencies**
   - Keep dependencies updated
   - Run `pip audit` regularly
   - Review dependency licenses

2. **Code Review**
   - All changes require review
   - Security-focused code review
   - Automated security scanning

3. **Input Validation**
   - Validate all inputs
   - Sanitize user data
   - Use parameterized queries

4. **Authentication**
   - Never log sensitive data
   - Use secure token storage
   - Implement rate limiting

## Known Security Considerations

### Authentication Tokens

- Tokens are stored in environment variables
- Tokens are never logged in plaintext
- Tokens are transmitted securely over HTTPS

### API Access

- All API calls require authentication
- Rate limiting is implemented
- CORS is properly configured

### Data Handling

- No sensitive data is cached
- All queries are validated
- Error messages don't expose internals

## Security Updates

Security updates will be released as soon as possible:

- **Critical**: Within 24 hours
- **High**: Within 1 week
- **Medium**: Within 1 month
- **Low**: Next regular release

## Vulnerability Disclosure Timeline

1. **Day 0**: Vulnerability reported
2. **Day 1**: Acknowledgment sent
3. **Day 7**: Initial assessment complete
4. **Day 30**: Fix in development
5. **Day 60**: Fix testing
6. **Day 90**: Public disclosure (if fixed)

## Security Hall of Fame

We thank the following researchers for responsibly disclosing security issues:

<!-- Names will be added as vulnerabilities are reported and fixed -->

*No vulnerabilities reported yet.*

## Contact

For security issues: security@nife.io
For other issues: support@nife.io

## PGP Key

For encrypted communications, use our PGP key:

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
[PGP key will be added]
-----END PGP PUBLIC KEY BLOCK-----
```

---

**Last Updated**: November 9, 2025
