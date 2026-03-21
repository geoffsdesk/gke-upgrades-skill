# Pre-Upgrade Checklist - Autopilot Production Clusters

```
Pre-Upgrade Checklist: Prod Autopilot 1.31 → 1.32
- [x] Cluster Mode: Autopilot | Channel: Stable 
- [x] Current version: 1.31 | Target version: 1.32

Compatibility
- [ ] 1.32 available in Stable channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.31 → 1.32 breaking changes
- [ ] Third-party operators/controllers compatible with K8s 1.32
- [ ] Admission webhooks tested against 1.32 (if any)

Workload Readiness
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown
- [ ] **Resource requests set on ALL containers (mandatory for Autopilot)**
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database operators (if any) compatible with K8s 1.32

Dev Environment Validation
- [ ] Dev clusters (Rapid channel) already running 1.32+ successfully
- [ ] Application smoke tests passed on dev 1.32 clusters
- [ ] No regressions observed in dev after 1.32 upgrade
- [ ] Performance baselines captured from dev clusters

Upgrade Timing & Controls
- [ ] Maintenance window configured for off-peak hours
- [ ] Auto-upgrade timing acceptable (check upgrade-info API for target dates)
- [ ] **Consider maintenance exclusion if upgrade timing conflicts with critical business periods:**
      - "No minor or node upgrades" (allows CP patches, up to EoS)
      - "No upgrades" (30-day max, blocks everything - use for code freezes)
- [ ] Stakeholder communication sent about expected upgrade timing
- [ ] Scheduled upgrade notifications enabled (72h advance warning via Cloud Logging)

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput) 
- [ ] On-call team aware of upgrade window
- [ ] Rollback plan documented (primarily workload-level)
- [ ] **Autopilot limitation noted: No SSH access to nodes, debugging via Cloud Logging only**
```

# Post-Upgrade Checklist - Autopilot Production Clusters

```
Post-Upgrade Checklist: Autopilot 1.31 → 1.32

Control Plane Health (Autopilot manages nodes automatically)
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"`
- [ ] All nodes automatically upgraded to 1.32: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] **Autopilot system pods updated:** `kubectl get pods -n gke-system`
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces`

Workload Health  
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] **Resource requests still valid** (Autopilot may adjust them)
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/load balancers responding
- [ ] Application health checks and smoke tests passing

Observability
- [ ] Metrics pipeline active, no collection gaps  
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] **GKE Autopilot insights showing healthy cluster state**

Cleanup & Documentation
- [ ] Upgrade documented in changelog
- [ ] Lessons learned captured for next upgrade cycle
- [ ] **Verify dev clusters still on newer version for future testing**
- [ ] Consider updating dev clusters to next available version for continued validation
```

## Key Autopilot-Specific Notes

**Simplified Operations:** Since you're on Autopilot, you don't need to worry about:
- Node pool upgrade strategies (surge settings, blue-green)
- Node SSH access or manual node management  
- Quota management for surge nodes
- Node-level troubleshooting

**Resource Requests Critical:** Autopilot requires resource requests on all containers. Missing requests will cause pod rejection after upgrade.

**Dev-First Validation:** Your Rapid dev clusters are perfect canaries. Since Rapid gets 1.32 weeks before Stable, use this time to validate your workloads thoroughly.

**Maintenance Window Strategy:** For predictable timing, configure maintenance windows rather than waiting for random auto-upgrade timing within the month.

Would you like me to create specific `gcloud` commands for checking your cluster status or configuring maintenance windows?