# Deployment Procedure

## Overview

This document outlines the standard procedure for deploying applications to production.

## Pre-Deployment Checklist

- [ ] All tests passing in CI
- [ ] Code review approved
- [ ] Security scan completed
- [ ] Documentation updated
- [ ] Database migrations tested
- [ ] Rollback plan prepared

## Deployment Steps

### 1. Preparation

```bash
# Ensure you're on the correct branch
git checkout main
git pull origin main

# Verify the release tag
git tag -l | grep v1.x.x
```

### 2. Staging Deployment

1. Deploy to staging environment first
2. Run smoke tests
3. Verify all functionality
4. Monitor logs for errors
5. Get QA sign-off

### 3. Production Deployment

```bash
# Trigger deployment pipeline
./deploy.sh production v1.x.x

# Or via CI/CD
# Merge to main triggers automatic deployment
```

### 4. Post-Deployment Verification

1. Check application health endpoints
2. Verify critical user flows
3. Monitor error rates
4. Check performance metrics
5. Confirm logs are flowing

## Rollback Procedure

If issues are detected:

```bash
# Immediate rollback
./rollback.sh production v1.x.x-previous

# Or via dashboard
# Navigate to Deployments > Rollback
```

## Deployment Windows

- **Standard deployments**: Tuesday-Thursday, 10:00-16:00
- **Emergency fixes**: Any time with on-call approval
- **No deployments**: Fridays after 14:00, weekends, holidays

## Monitoring

- Dashboard: https://monitoring.internal
- Alerts: #alerts-production channel
- On-call: PagerDuty rotation

## Contact

DevOps Team: devops@company.com
On-call: See PagerDuty schedule
