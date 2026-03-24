# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) + 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (minor version upgrade)  
**Mode:** Autopilot (Google manages nodes automatically)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: 2 dev (Rapid) + 2 prod (Stable) | All Autopilot
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Breaking Changes
- [ ] 1.32 available in Stable channel (`gcloud container get-server-config --region REGION --format="yaml(channels)"`)
- [ ] No deprecated API usage in ANY cluster (check GKE deprecation insights dashboard for all 4 clusters)
- [ ] Kubernetes 1.32 release notes reviewed for breaking changes
- [ ] Third-party operators/controllers compatible with K8s 1.32 (cert-manager, ingress controllers, monitoring, etc.)
- [ ] Admission webhooks tested against 1.32 (cert-manager webhooks are common failure points)

Autopilot-Specific Readiness
- [ ] ALL containers have resource requests (mandatory in Autopilot - missing requests = pod rejection)
- [ ] No privileged containers or host-level configurations (not supported in Autopilot)
- [ ] terminationGracePeriodSeconds ≤ 600s for regular pods, ≤ 25s for Spot pods (Autopilot hard limits)
- [ ] PDBs configured but not overly restrictive (Autopilot respects PDBs for up to 1 hour)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs

Dev Environment Validation (Should already be on 1.32)
- [ ] Dev clusters already upgraded to 1.32 via Rapid channel
- [ ] Application functionality verified on 1.32 in dev
- [ ] No issues with workload compatibility observed in dev
- [ ] Performance baseline captured from dev on 1.32

Infrastructure & Timing
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Consider maintenance exclusion if upgrade timing conflicts with critical business periods:
      - "No upgrades" (30-day max) for complete freeze
      - "No minor upgrades" (up to EoS) to allow patches but block 1.32
- [ ] Auto-upgrade target confirmed (`gcloud container clusters get-upgrade-info CLUSTER --region REGION`)
- [ ] Scheduled upgrade notifications configured (72h advance notice via Cloud Logging - preview feature)

Observability & Operations
- [ ] Monitoring active for all 4 clusters (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput) for prod workloads
- [ ] Log aggregation functioning (Cloud Logging or external)
- [ ] Alerting rules updated for any new K8s 1.32 metrics/labels
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware and available during prod upgrade window
- [ ] Rollback plan documented (control plane rollback requires GKE support for minor versions)
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Control Plane Health
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Auto-upgrade status normal: `gcloud container clusters get-upgrade-info CLUSTER --region REGION`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] API server responding normally (no 503s or high latency)

Node Health (Google-managed)
- [ ] Nodes auto-upgraded to 1.32: `kubectl get nodes -o wide`
- [ ] All nodes Ready status: `kubectl get nodes`
- [ ] No nodes stuck in NotReady or SchedulingDisabled
- [ ] Node system pods running: `kubectl get pods -n kube-system -o wide`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completing successfully: `kubectl get jobs -A`
- [ ] No stuck PDBs: `kubectl get pdb -A`

Application Functionality
- [ ] Ingress/load balancers responding correctly
- [ ] External traffic routing properly
- [ ] Application health checks passing
- [ ] Database connections stable (if applicable)
- [ ] API endpoints returning expected responses
- [ ] Authentication/authorization working (RBAC, service accounts)

Autopilot-Specific Validation
- [ ] Resource requests still honored (no pod rejections)
- [ ] Autopilot node scaling working normally
- [ ] No unexpected node pool changes
- [ ] Pod security standards enforced correctly
- [ ] Network policies functioning (if used)

Observability & Performance
- [ ] Metrics collection resumed (no gaps in time series)
- [ ] Logs flowing to aggregation systems
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency percentiles (p50/p95/p99) within acceptable range
- [ ] Resource utilization patterns normal
- [ ] Custom dashboards displaying correctly

Cleanup & Documentation
- [ ] Temporary maintenance exclusions removed (if applied)
- [ ] Upgrade completed in change management system
- [ ] Post-upgrade lessons learned documented
- [ ] Team notified of successful completion
- [ ] Monitor for 24-48 hours for any delayed issues
```

## Key Autopilot Considerations

**What Google handles automatically:**
- Node pool upgrades (you can't control surge settings)
- Node OS updates and security patches  
- Node scaling and pod bin packing
- System addon updates

**What you control:**
- Control plane upgrade timing (via maintenance windows/exclusions)
- Workload readiness (resource requests, PDBs, graceful shutdown)
- Application compatibility validation

**Upgrade sequence recommendation:**
1. Verify dev clusters on 1.32 are stable
2. Upgrade prod cluster #1 during maintenance window
3. Validate thoroughly, wait 24-48h
4. Upgrade prod cluster #2

**Common Autopilot upgrade issues:**
- Missing resource requests causing pod rejection
- Admission webhooks (esp. cert-manager) incompatible with 1.32
- PDBs too restrictive blocking node drain
- Applications assuming specific node configurations

Since your dev clusters should already be on 1.32 via Rapid channel, use them to validate workload compatibility before the prod upgrade!