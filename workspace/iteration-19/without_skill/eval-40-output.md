Moving all clusters to "No channel" isn't generally recommended, especially coming from Regular channel. Here's why and what you should consider:

## Problems with "No channel" approach:

**Security risk**: You become responsible for tracking and applying critical security patches manually. GKE channels automatically include security updates.

**Maintenance overhead**: You'll need to manually monitor GKE release notes, plan upgrades, and ensure compatibility across your fleet.

**Version support**: Google only supports a limited number of versions. Without channel updates, you might find yourself forced into emergency upgrades.

## Better alternatives for upgrade control:

### 1. **Static channel** (Recommended starting point)
```yaml
# Slower, more predictable updates
releaseChannel:
  channel: STABLE
```

### 2. **Maintenance windows** with Regular channel
```yaml
maintenancePolicy:
  window:
    recurringWindow:
      window:
        startTime: "2023-01-01T09:00:00Z"
        endTime: "2023-01-01T17:00:00Z"
      recurrence: "FREQ=WEEKLY;BYDAY=SA"
```

### 3. **Node pool management**
```yaml
# Disable auto-upgrade on node pools, keep control plane on channel
nodePool:
  management:
    autoUpgrade: false
    autoRepair: true
```

## Recommended approach:
1. Start with **Stable channel** instead of No channel
2. Use **maintenance windows** to control timing
3. Implement proper **testing pipelines** for upgrades
4. Consider **no channel only for specific clusters** that need it (like production clusters with strict change control)

This gives you more control while maintaining security updates. What's your specific concern with the Regular channel's upgrade timing?