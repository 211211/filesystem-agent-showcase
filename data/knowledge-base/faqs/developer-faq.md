# Developer FAQ

## General Questions

### Q: How do I set up my development environment?

Follow the setup guide in the project README. Generally:
1. Clone the repository
2. Copy `.env.example` to `.env`
3. Run `npm install` or `pip install -r requirements.txt`
4. Start the development server

### Q: Where do I find API documentation?

- Swagger/OpenAPI docs are available at `/docs` when running locally
- Additional documentation is in the `docs/` folder of each project
- Wiki pages are available on GitHub

### Q: How do I run tests?

```bash
# JavaScript projects
npm test
npm run test:coverage

# Python projects
pytest
pytest --cov=app
```

## Code & Git

### Q: What's the branch naming convention?

- `feature/TICKET-123-description` for features
- `bugfix/TICKET-123-description` for bug fixes
- `hotfix/description` for urgent production fixes

### Q: How do I get my PR reviewed?

1. Ensure CI passes
2. Add appropriate reviewers
3. Fill out the PR template
4. Link related issues
5. Request review in #code-review channel if urgent

### Q: What's the commit message format?

```
[TICKET-123] Short description

Longer description if needed.
- Bullet points for details
- What changed and why
```

## Authentication

### Q: How do I test with authentication locally?

Use the test credentials in `.env.example` or generate a JWT token:
```bash
npm run generate-token -- --user test@example.com
```

### Q: How do I add a new API key?

1. Contact DevOps for production keys
2. For development, generate via the admin panel
3. Store in `.env` file (never commit!)

## Debugging

### Q: How do I debug API issues?

1. Check logs: `docker-compose logs -f api`
2. Enable debug mode: set `DEBUG=true`
3. Use the `/health` and `/debug` endpoints
4. Check database connectivity

### Q: Where are the logs stored?

- Local: `./logs/` directory
- Production: CloudWatch/Datadog
- Access via monitoring dashboard

## Infrastructure

### Q: How do I connect to the database?

```bash
# Local
psql postgresql://localhost:5432/mydb

# Production (requires VPN)
# Use credentials from 1Password
```

### Q: How do I access production?

1. Connect to VPN
2. Use SSH with your registered key
3. Follow the access procedure in wiki

## Getting Help

- Slack: #dev-help
- On-call: Check PagerDuty schedule
- Documentation: wiki.internal/docs
