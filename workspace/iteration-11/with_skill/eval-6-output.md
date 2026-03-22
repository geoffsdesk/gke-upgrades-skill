# Moving Production Cluster from Rapid to Stable Channel

## Key Implications

### Version Availability Impact
- **Current situation**: You're on 1.32 in Rapid channel
- **After migration**: You'll be on 1.32 in Stable channel
- **Version lag**: Stable channel receives versions ~4-8 weeks after Rapid
- **Future upgrades**: You'll get new versions later but with better stability validation

### SLA and Stability Changes
- **Rapid channel**: No SLA for upgrade stability - versions may have issues caught before reaching Regular/Stable
- **Stable channel**: Full SLA coverage with maximum stability validation
- **This is likely the PRIMARY reason for your CTO's request** - production workloads should have SLA coverage

### Auto-upgrade Timing
- **Immediate effect**: Your auto-upgrade cadence will slow down significantly
- **Maintenance windows/exclusions**: Will continue to work the same way
- **Version progression**: You'll follow the Stable channel upgrade schedule going forward

## Migration Process

### Step 1: Verify Current State
```bash
# Check current channel and version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check what versions are available in Stable
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.STABLE)"
```

### Step 2: Execute Channel Migration
```bash
# Migrate to Stable channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

**Important**: This operation only changes the channel enrollment - it does NOT trigger an immediate version change. Your cluster stays at 1.32.

### Step 3: Verify Migration
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check new auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE
```

## What Happens Next

### Immediate (Day 0-7)
- Cluster remains at 1.32
- No version changes
- Auto-upgrade schedule switches to Stable cadence
- SLA coverage now applies to future upgrades

### Medium-term (Weeks 2-8)
- Your cluster will NOT be auto-upgraded until 1.32 becomes the auto-upgrade target in Stable channel
- You'll likely stay at 1.32 longer than you would have on Rapid
- New patches for 1.32 will arrive via Stable channel schedule

### Long-term
- Future minor version upgrades (1.33, 1.34, etc.) will arrive weeks later than Rapid
- But they'll be much more stable and carry full SLA

## Alternative Approach: Regular Channel

Consider **Regular channel** as a middle ground:
- Full SLA coverage (unlike Rapid)
- Faster than Stable but slower than Rapid
- Good balance for most production workloads
- Default choice for new clusters

```bash
# Alternative: migrate to Regular instead
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

## Maintenance Exclusions Strategy

Since you're moving to a slower channel, consider configuring maintenance exclusions for maximum control:

```bash
# Add "no minor or node upgrades" exclusion for tight control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "production-control" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+6 months" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows security patches but blocks disruptive upgrades until you're ready.

## Risk Assessment

### Low Risk
- Channel migration itself is a metadata change
- No immediate version impact
- Can revert if needed

### Consider
- Your upgrade velocity will slow significantly - ensure this aligns with security patching requirements
- Test the migration in a dev/staging cluster first
- Communicate the change to your team - they'll see different upgrade timing

## Next Steps Recommendation

1. **Test in non-production first**: Apply the same channel change to dev/staging
2. **Execute during low-traffic period**: Though low-risk, do this during a maintenance window
3. **Monitor**: Watch the auto-upgrade target changes over the next few weeks
4. **Document**: Update your runbooks to reflect the new channel strategy

The migration is straightforward and aligns with production best practices. Your CTO is making the right call for stability and SLA coverage.