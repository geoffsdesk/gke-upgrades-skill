# GKE 1.29 to 1.30 Upgrade Checklists

**Environment:** 4 Autopilot Clusters (2 Dev/Rapid, 2 Prod/Stable)
**Upgrade Window:** April 2026 (Prod auto-upgrade)

---

## Pre-Upgrade Checklist

### Phase 1: Assessment & Planning (2-3 weeks before)

#### Cluster Inventory
- [ ] Document all 4 cluster names, regions, and current versions
- [ ] Verify prod clusters are on Stable channel (auto-upgrade scheduled)
- [ ] Verify dev clusters on Rapid channel (likely upgraded already or soon)
- [ ] Confirm all clusters are Autopilot (no node pool management needed)

#### Compatibility Review
- [ ] Check Kubernetes 1.30 release notes for breaking changes
- [ ] Review deprecated APIs that will be removed in 1.30:
  - [ ] Flow control API v1beta2 → v1 migration
  - [ ] Check if any controllers use flow control
- [ ] Audit workloads for use of removed/deprecated features
  - [ ] Search for beta APIs in use across all namespaces
  - [ ] Check addon configurations (Istio, Flux, etc.)
- [ ] Test dev clusters first (they upgrade to 1.30 on Rapid automatically)

#### Dependency Updates
- [ ] Verify all container images have 1.30 compatibility (check CVEs)
- [ ] Update Helm charts to 1.30-compatible versions
- [ ] Review addon versions (CNI, monitoring, logging) for 1.30 support
- [ ] Check workload manifest compatibility:
  - [ ] RBAC policies and network policies
  - [ ] Pod Security Standards (PSS) enforcement levels
- [ ] Validate custom webhooks (mutating/validating) work with 1.30 API groups

#### Testing in Dev
- [ ] Schedule test window on dev clusters (Rapid channel will upgrade automatically)
- [ ] Prepare test plan for prod workload simulation
- [ ] Validate critical application paths after dev upgrade completes
- [ ] Document any behavioral changes or warnings observed

#### Backup & Recovery
- [ ] Verify backup solution is configured (Backup for GKE or similar)
- [ ] Test backup restore procedure on non-critical cluster
- [ ] Document rollback procedures (though Autopilot doesn't allow downgrade)
- [ ] Ensure persistent data is backed up

### Phase 2: Communication (1-2 weeks before prod upgrade)

#### Stakeholder Notification
- [ ] Notify application teams of upgrade window (prod: April 2026)
- [ ] Share expected downtime (typically minimal for Autopilot, but possible)
- [ ] Document temporary performance degradation expectations
- [ ] Provide escalation contacts for issues during upgrade

#### Production Readiness
- [ ] Verify both prod clusters are healthy (all nodes ready, no pending pods)
- [ ] Check resource utilization isn't near limits
- [ ] Ensure cluster autoscaler is functioning properly
- [ ] Validate monitoring and alerting are all green

---

## Post-Upgrade Checklist

### Phase 1: Immediate Validation (Within 2 hours after upgrade)

#### Cluster Health
- [ ] Verify control plane is healthy on both prod clusters
- [ ] Check node pool status (Autopilot managed, but verify):
  - [ ] All nodes are Ready
  - [ ] No NotReady or Unknown states
  - [ ] Node version matches expected 1.30.x
- [ ] Confirm Kubernetes version: `kubectl version`
- [ ] Check API server logs for errors: `kubectl logs -n kube-system -l component=kube-apiserver`

#### System Component Validation
- [ ] Verify core system pods are running:
  - [ ] coredns
  - [ ] kube-proxy
  - [ ] CNI daemonset (GKE managed)
  - [ ] Metrics-server
  - [ ] kube-controller-manager
- [ ] Check for CrashLoopBackOff or pending pods: `kubectl get pods -A`
- [ ] Validate addon status in GKE console
- [ ] Confirm Workload Identity is functioning (test a service account)

#### Network & Storage
- [ ] Test pod-to-pod communication across nodes
- [ ] Verify service discovery (DNS resolution)
- [ ] Validate PVC mounts and persistent storage operations
- [ ] Test ingress functionality (HTTP/HTTPS)

### Phase 2: Application Validation (2-6 hours post-upgrade)

#### Workload Health
- [ ] Validate all critical application pods are running
- [ ] Check pod restart counts (should be stable, not escalating)
- [ ] Monitor resource usage (CPU, memory) for anomalies
- [ ] Verify no pending or failed pod events: `kubectl describe node`
- [ ] Check application logs for errors or warnings

#### Functionality Testing
- [ ] Run smoke tests for critical application features
- [ ] Validate integrations with external services
- [ ] Test database connectivity and operations
- [ ] Confirm scheduled jobs (CronJobs) are working
- [ ] Validate webhook invocations (if any custom webhooks)

#### API & Feature Testing
- [ ] Test APIs that depend on new 1.30 features (if applicable)
- [ ] Verify deprecated features still work (with warnings if expected)
- [ ] Confirm RBAC policies are still enforced correctly
- [ ] Validate network policies are effective
- [ ] Test Pod Security Standards enforcement

### Phase 3: Observability & Monitoring (6-24 hours post-upgrade)

#### Metrics & Logs
- [ ] Review cluster metrics (API latency, etcd performance)
- [ ] Check error rates haven't increased
- [ ] Monitor GCP billing/cost for unexpected spikes
- [ ] Validate all logging/monitoring exporters are operational
- [ ] Confirm Prometheus/Datadog/equivalent is scraping metrics

#### Performance Validation
- [ ] Run performance test/load test on at least one prod cluster
- [ ] Compare baseline metrics from pre-upgrade
- [ ] Validate cluster auto-scaling behavior under load
- [ ] Check network throughput and latency

#### Production Stability Window
- [ ] Monitor both prod clusters for 24 hours post-upgrade
- [ ] Have on-call engineer available for quick response
- [ ] Document any issues encountered
- [ ] Validate both prod clusters pass post-upgrade checks

### Phase 4: Final Cleanup & Documentation (24-48 hours post-upgrade)

#### Cleanup Tasks
- [ ] Remove temporary test namespaces/resources if created
- [ ] Clean up any debug/diagnostic resources
- [ ] Update cluster documentation with new version

#### Documentation & Rollup
- [ ] Document actual upgrade duration and impact
- [ ] Record any issues encountered and resolutions
- [ ] Update runbooks with any new operational considerations
- [ ] Share post-upgrade report with team
- [ ] Validate backup system captured upgraded cluster state

#### Autopilot-Specific Validation
- [ ] Verify node auto-repairs still function post-upgrade
- [ ] Confirm cluster auto-scaling thresholds are appropriate
- [ ] Validate Autopilot maintenance windows are still scheduled
- [ ] Ensure no unexpected node replacements occurring

---

## Environment-Specific Notes

### Dev Clusters (Rapid Channel)
- Upgrade happens automatically on Rapid schedule (typically monthly)
- Use as validation environment for prod procedures
- Monitor post-upgrade to identify any issues before prod upgrade
- Can test new Kubernetes features earlier

### Prod Clusters (Stable Channel)
- Upgrade scheduled for April 2026 (exact date TBD)
- Google controls upgrade timing, but will notify in advance
- Expect minimal downtime (typically <10 minutes for Autopilot)
- Both prod clusters upgrade on same schedule; plan accordingly
- Monitor closely for first 24 hours after each cluster upgrades

---

## Common Issues & Troubleshooting

| Issue | Check | Solution |
|-------|-------|----------|
| Pods not scheduling post-upgrade | Node affinity rules, taints/tolerations | Review node labels changed in 1.30 |
| API call failures | Deprecated API usage | Migrate to stable API versions |
| Webhook timeouts | Webhook configurations | Increase timeouts if needed, validate cert rotation |
| Metric collection failures | Monitoring agents | Restart/upgrade monitoring sidecars |
| etcd performance degradation | etcd version | Verify etcd upgraded correctly (usually transparent in Autopilot) |

---

## Rollback Considerations

**Important:** Autopilot clusters cannot be downgraded. If critical issues arise:
1. Google will provide hot patches or rollback if systemic issue identified
2. Full rollback requires restoring from backup and losing post-upgrade data
3. Plan to prevent issues rather than plan for rollback

This reinforces the importance of thorough testing on dev clusters first.
