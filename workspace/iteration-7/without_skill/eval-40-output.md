Moving all clusters to "No channel" for maximum upgrade control can be risky and is generally not recommended as a blanket approach. Here's why:

## Downsides of "No channel"

**Security vulnerabilities**: You become responsible for tracking and applying critical security patches manually - these can't wait for your preferred timeline.

**Operational overhead**: You'll need to:
- Monitor GKE release notes constantly
- Test each upgrade thoroughly
- Plan and execute upgrades manually
- Track which clusters are on which versions

**Support limitations**: Google provides limited support for very old versions, and you might miss important bug fixes.

## Better alternatives for controlled upgrades

### 1. **Rapid Channel + Maintenance Windows**
```yaml
# More control while staying current
maintenancePolicy:
  window:
    recurringWindow:
      schedule: "FREQ=WEEKLY;BYDAY=SU"
      startTime: "2023-01-01T09:00:00Z"
      endTime: "2023-01-01T17:00:00Z"
```

### 2. **Custom Release Channels**
- Use Rapid channel for dev/staging
- Use Regular channel for production
- Test upgrades in lower environments first

### 3. **Staged approach**
```bash
# Upgrade node pools separately from control plane
gcloud container clusters upgrade CLUSTER_NAME --master
# Test, then upgrade nodes
gcloud container node-pools upgrade POOL_NAME --cluster=CLUSTER_NAME
```

## Recommended approach
- Keep Regular channel for production
- Use maintenance windows for timing control
- Implement proper testing pipelines
- Only use "No channel" for specific clusters that truly need it (legacy apps, compliance requirements)

What's your main concern with Regular channel upgrades? There might be other ways to address your control needs.