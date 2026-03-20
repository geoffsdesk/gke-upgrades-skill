# GKE Fleet Modernization Plan

You've inherited a common scenario - technical debt accumulation in GKE fleets. Here's a systematic approach to assess, prioritize, and modernize your clusters using GKE's self-service tools.

## Phase 1: Discovery and Assessment

### Fleet visibility with GKE Dashboard and APIs

**Start with the GKE clusters dashboard** in the Google Cloud Console. This gives you fleet-wide visibility:
- Cluster versions, release channels, and upgrade status
- Security posture indicators
- Resource utilization patterns
- Deprecated API usage alerts

**Command-line fleet inventory:**
```bash
# Generate fleet inventory across all projects/regions
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label='CHANNEL',
  nodePools[].version.list():label='NODE_VERSIONS',
  status
)" > fleet-inventory.csv

# Identify legacy "No channel" clusters
gcloud container clusters list --filter="releaseChannel.channel=''" \
  --format="value(name,location,currentMasterVersion)"

# Find clusters approaching End of Support
gcloud container clusters list --format="csv(name,location,currentMasterVersion)" | \
  grep -E "1\.2[4-6]\." # Adjust version pattern as needed
```

### GKE deprecation insights

**Enable deprecation insights** - this is your most critical assessment tool:
- Navigate to GKE → [Cluster Name] → Observability → Insights
- Shows deprecated API usage that will break upgrades
- Provides workload-specific remediation guidance
- Available via API: `gcloud container clusters describe CLUSTER --zone ZONE --format="yaml(conditions)"`

### Security posture assessment

**GKE Security Posture dashboard** (if enabled):
- Shows security findings across your fleet
- Identifies clusters with outdated security policies
- Binary Authorization policy compliance

**Quick security check via CLI:**
```bash
# Check for clusters without Workload Identity
gcloud container clusters list --filter="workloadIdentityConfig.workloadPool=''" \
  --format="value(name,location)"

# Identify clusters with legacy ABAC enabled
gcloud container clusters list --filter="legacyAbac.enabled=true" \
  --format="value(name,location)"
```

### Cost and utilization analysis

**GKE usage metering** (enable if not active):
```bash
gcloud container clusters update CLUSTER_NAME --zone ZONE --enable-network-policy --enable-ip-alias --enable-resource-usage-export
```

**Node pool rightsizing recommendations:**
- Check the GKE Recommendations tab in each cluster
- Look for oversized node pools and underutilized resources
- Use `kubectl top nodes` for real-time utilization

## Phase 2: Risk-Based Prioritization

### Categorize clusters by risk level

**Critical (upgrade immediately):**
- Versions at or past End of Support
- Clusters with deprecated API usage blocking upgrades  
- Production workloads on unsupported versions
- No channel clusters running < 1.27

**High (upgrade within 30 days):**
- Versions 1-2 patches behind current
- Missing security features (Workload Identity, Binary Authorization)
- Dev/staging clusters significantly behind production

**Medium (upgrade within 60 days):**
- Minor version behind but within support window
- Functional but suboptimal configurations (legacy RBAC, basic auth)

**Low (modernize during maintenance windows):**
- Recent versions but on suboptimal release channels
- Missing nice-to-have features (GKE Autopilot candidates)

### Workload impact assessment

**Identify stateful workloads requiring extra care:**
```bash
# Find StatefulSets and persistent volumes
kubectl get statefulsets -A
kubectl get pv -A | grep -v Available

# Check for long-running jobs/batch workloads
kubectl get jobs -A --field-selector=status.active>0
```

## Phase 3: Modernization Strategy

### Standard → Autopilot migration candidates

**Autopilot is ideal for:**
- Stateless web applications
- CI/CD workloads  
- Microservices without special node requirements
- Teams wanting hands-off infrastructure

**Assessment command:**
```bash
# Check Autopilot compatibility
gcloud container clusters describe CLUSTER --zone ZONE --format="yaml(autopilot)"
# Look for workloads using features unavailable in Autopilot (SSH access, privileged containers, custom node images)
```

### Release channel strategy

**Recommended channel mapping:**
- **Dev/test environments:** Rapid channel (earliest access to features)
- **Staging:** Regular channel (default, balanced stability/features) 
- **Production:** Stable channel (maximum stability) or Regular for faster security patches
- **Compliance-heavy prod:** Extended channel (24-month support, extra cost)

**Migration from legacy "No channel":**
```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel regular

# For maximum control: Extended channel
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel extended
```

### Maintenance window standardization

**Implement consistent maintenance windows:**
```bash
# Example: Saturday 2-6 AM UTC for prod clusters
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Phase 4: Self-Service Tools and Automation

### GKE upgrade assist and recommendations

**Enable upgrade assist** (for clusters 1.27+):
- Provides upgrade impact analysis
- Pre-upgrade compatibility checks
- Workload-specific guidance

**Access via console:** GKE → [Cluster] → Operations → Upgrade assist

### Rollout sequencing for large fleets

**For 10+ clusters,** consider GKE rollout sequencing:
```bash
# Create upgrade sequence: dev → staging → prod with soak time
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --enable-managed-prometheus \
  --rollout-sequencing-configuration-file rollout-config.yaml
```

**Note:** Rollout sequencing is an advanced feature. For most fleets, prefer simpler approaches like staggered maintenance windows across environments.

### Monitoring and alerting setup

**Essential monitoring:**
```bash
# Enable Cloud Operations for GKE
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --enable-cloud-logging \
  --enable-cloud-monitoring
```

**Set up version drift alerts:**
- Use Cloud Monitoring to alert when clusters fall >2 minor versions behind
- Monitor deprecated API usage metrics
- Track upgrade success/failure rates

### Policy and governance

**Implement Organization Policy constraints:**
```yaml
# Example: Require release channel enrollment
constraint: constraints/gcp.resourceLocations
listPolicy:
  allowedValues:
  - "projects/*/locations/*/clusters/*"
  deniedValues:
  - "projects/*/locations/*/clusters/*:releaseChannel.channel=''"
```

**Binary Authorization for container security:**
```bash
gcloud container binauthz policy import policy.yaml
```

## Phase 5: Execution Templates

### Critical cluster upgrade runbook

**For clusters at/past EoS:**
```bash
# 1. Assess deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 2. Migrate to release channel first
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel regular

# 3. Set maintenance window
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z"

# 4. Sequential upgrade (don't skip minors)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version TARGET_VERSION
# Wait for control plane, then:
gcloud container node-pools upgrade NODE_POOL --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
```

### Fleet modernization checklist

```
Fleet Modernization Checklist
- [ ] Complete discovery and risk assessment across all clusters
- [ ] Migrate all legacy "No channel" clusters to release channels
- [ ] Establish consistent maintenance windows per environment tier
- [ ] Enable deprecation insights and upgrade assist on all clusters ≥1.27
- [ ] Implement monitoring for version drift and EoS notifications
- [ ] Evaluate Standard → Autopilot migration opportunities
- [ ] Set up policy guardrails to prevent future configuration drift
- [ ] Document cluster inventory and upgrade procedures for the team
- [ ] Establish regular fleet health reviews (monthly recommended)
```

## Long-term Fleet Health

### Prevent future drift

**Organization policies:** Enforce release channel enrollment, region restrictions, and security baselines
**Infrastructure as Code:** Manage clusters via Terraform/Config Connector rather than manual changes  
**Regular auditing:** Monthly reviews of cluster versions, security posture, and cost optimization opportunities

### Self-service tooling recommendations

1. **GKE dashboard** - Primary interface for fleet visibility
2. **Deprecation insights** - Your early warning system for upgrade blockers  
3. **GKE recommendations** - Built-in rightsizing and optimization suggestions
4. **Cloud Asset Inventory** - Query fleet metadata programmatically
5. **Release schedule** - https://cloud.google.com/kubernetes-engine/docs/release-schedule for planning

This systematic approach will transform your inherited technical debt into a well-managed, secure, and cost-effective GKE fleet. Focus on the critical/high-risk clusters first, then systematically work through the modernization backlog.