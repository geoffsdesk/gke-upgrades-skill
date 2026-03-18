# GKE Autopilot 1.29 to 1.30 Upgrade Checklists

## Overview

This document provides pre and post-upgrade checklists tailored to your GKE Autopilot infrastructure:
- **2 Dev Clusters** on Rapid release channel
- **2 Prod Clusters** on Stable release channel

The upgrade from Kubernetes 1.29 to 1.30 will occur automatically during your configured maintenance windows. Key changes in 1.30 include removal of flowcontrol.apiserver.k8s.io/v1beta3 and legacy storage classes.

---

## Pre-Upgrade Checklist (4-6 weeks before)

### Phase 1: Planning & Communication (Week -4 to -3)

- [ ] **Notify stakeholders** of the scheduled upgrade window (prod clusters will auto-upgrade in ~1 month)
- [ ] **Review Kubernetes 1.30 release notes** for breaking changes and new features
- [ ] **Check GKE deprecations page** for any APIs or features removed in 1.30
  - Focus on: flowcontrol.apiserver.k8s.io/v1beta3 removal, storage class changes
- [ ] **Document current cluster versions** for all 4 clusters (2 dev, 2 prod)
- [ ] **Assess upgrade impact** on workloads by reviewing:
  - All deployed API object versions
  - Storage class usage across clusters
  - Custom admission controllers or flow control configurations

### Phase 2: API & Deprecation Audit (Week -3 to -2)

- [ ] **Run deprecation audits** on all 4 clusters using GKE's Deprecation Insights feature
  - [ ] Dev Cluster 1 (Rapid)
  - [ ] Dev Cluster 2 (Rapid)
  - [ ] Prod Cluster 1 (Stable)
  - [ ] Prod Cluster 2 (Stable)

- [ ] **Identify deprecated APIs in use** - prioritize:
  - flowcontrol.apiserver.k8s.io/v1beta3 → migrate to v1
  - Legacy storage classes (4k, 8k, 16k, v1-dynamic-40) → migrate to v2 classes
  - Any other deprecated APIs from 1.29 release

- [ ] **Audit workload configurations** that may impact upgrade duration:
  - [ ] Check all Pods with `terminationGracePeriodSeconds > 30s`
  - [ ] Review PodDisruptionBudgets (overly conservative policies may slow upgrades)
  - [ ] Identify node affinity constraints that could block node rotation
  - [ ] List all PersistentVolumes attached to pods (may slow graceful shutdown)

- [ ] **Export audit results** and share with development teams for remediation planning

### Phase 3: Testing & Mitigation (Week -2 to -1)

- [ ] **Update deprecated APIs** in all manifests:
  - [ ] Dev Cluster 1 - migrate flow control configuration
  - [ ] Dev Cluster 2 - migrate flow control configuration
  - [ ] Test storage class migrations in dev clusters first
  - [ ] Validate new API versions work with applications

- [ ] **Optimize workload configurations:**
  - [ ] Reduce `terminationGracePeriodSeconds` where safe
  - [ ] Review and adjust PodDisruptionBudgets for upgrade-friendliness
  - [ ] Test pod eviction and rescheduling behavior
  - [ ] Document any required application changes

- [ ] **Compute Engine quota verification:**
  - [ ] Verify CE instance quota is below 90% on both prod clusters
  - [ ] Reserve additional quota if needed (Autopilot surge upgrades use extra resources)
  - [ ] Ensure no quota issues that could block parallel node upgrades

- [ ] **Verify storage class migration readiness:**
  - [ ] Test migrating PVCs from legacy to v2 storage classes (non-prod first)
  - [ ] Validate storage performance expectations post-migration
  - [ ] Plan any necessary PVC migration steps

### Phase 4: Pre-Upgrade Validation (1 week before)

- [ ] **Verify cluster health** on all 4 clusters:
  - [ ] All nodes are Ready and SchedulingDisabled=False
  - [ ] All kube-system and gke-system pods are Running
  - [ ] No persistent pod failures or pending pods
  - [ ] Check `kubectl get nodes` and `kubectl get pods -A`

- [ ] **Backup critical configurations:**
  - [ ] Export manifests for all critical workloads
  - [ ] Backup any custom metrics, alerts, or observability configs
  - [ ] Document static pod configurations (these won't be auto-recreated)

- [ ] **Review maintenance windows:**
  - [ ] Confirm maintenance windows are set for prod clusters
  - [ ] Verify they align with low-traffic periods
  - [ ] Check for any maintenance exclusions and their validity

- [ ] **Enable enhanced monitoring:**
  - [ ] Set up or verify alerting for node upgrade progress
  - [ ] Ensure you can monitor pod scheduling during surge upgrades
  - [ ] Prepare dashboards to track cluster health during upgrade

- [ ] **Test rollback procedures** (if applicable):
  - [ ] Understand that auto-upgrade cannot be rolled back
  - [ ] Ensure you can manually downgrade if critical issues arise
  - [ ] Document the manual downgrade process for the team

- [ ] **Final API & configuration validation:**
  - [ ] Re-run deprecation audits to confirm all issues are resolved
  - [ ] Perform dry-run on any kubectl apply commands with updated manifests
  - [ ] Test critical application workflows in dev clusters

---

## Pre-Upgrade Checklist - Dev Clusters (Rapid Channel)

Since your dev clusters are on the Rapid channel, they may upgrade before the Stable channel. Use them as a testing ground:

- [ ] **Deploy test workloads** that mirror prod architectures to dev clusters
- [ ] **Perform full end-to-end testing** in dev after they upgrade
  - [ ] Test all storage class migrations
  - [ ] Verify flow control behavior
  - [ ] Run integration tests
  - [ ] Validate observability (metrics, logs, tracing)

- [ ] **Document any compatibility issues** discovered during dev upgrades
- [ ] **Brief prod teams** on any unexpected changes or gotchas found

---

## Pre-Upgrade Checklist - Prod Clusters (Stable Channel)

- [ ] **Confirm no critical changes pending** in the 1-2 weeks before upgrade
- [ ] **Reduce deployment/release velocity** during upgrade week to minimize conflicts
- [ ] **Increase on-call staffing** for the upgrade window and 24 hours after
- [ ] **Brief application teams** of expected behavior during surge upgrades
  - Pod evictions will occur (be prepared for brief service impacts)
  - Nodes will cycle (up to 20 nodes in parallel during surge upgrade)

---

## During Upgrade: Monitoring Checklist

### For All Clusters

- [ ] **Monitor control plane upgrade** (appears as API server restarts):
  - [ ] Watch for brief API request latency spikes
  - [ ] Monitor for service account token validation changes
  - [ ] Verify no persistent API errors

- [ ] **Monitor node surge upgrades:**
  - [ ] Track pod eviction rate (should be gradual)
  - [ ] Verify pods reschedule successfully on remaining nodes
  - [ ] Monitor resource pressure (CPU, memory) during surge

- [ ] **Watch for concerning patterns:**
  - [ ] Pods stuck in Terminating state (beyond grace period)
  - [ ] Persistent node failures during upgrade
  - [ ] Unexpected pod evictions outside surge windows
  - [ ] CrashLoopBackOff or other pod errors

- [ ] **Verify network & DNS:**
  - [ ] DNS resolution continues to work
  - [ ] No unexpected network timeouts
  - [ ] Inter-pod communication remains healthy

---

## Post-Upgrade Checklist (Immediate - first 24 hours)

### Phase 1: Cluster Verification (0-2 hours post-upgrade)

- [ ] **Verify upgrade completion:**
  - [ ] All nodes report version 1.30.x with `kubectl get nodes`
  - [ ] Control plane is at 1.30.x
  - [ ] All nodes are in Ready state

- [ ] **Cluster health verification:**
  - [ ] Run `kubectl get nodes` - all should be Ready
  - [ ] Run `kubectl get pods -A` - verify no stuck pods
  - [ ] Check `kubectl get events -A --sort-by='.lastTimestamp'` for errors
  - [ ] Verify all system pods (kube-dns, logging, monitoring) are running

- [ ] **API server health:**
  - [ ] Verify API server is responding to requests
  - [ ] Check kubectl access from multiple sources
  - [ ] Validate RBAC is functioning correctly
  - [ ] Confirm webhook configurations are still valid

- [ ] **Workload validation:**
  - [ ] Verify all critical applications are Running
  - [ ] Check pod restart counts haven't spiked unexpectedly
  - [ ] Validate application logs for upgrade-related errors
  - [ ] Confirm service endpoints are populated correctly

### Phase 2: Application & Storage Validation (2-6 hours post-upgrade)

- [ ] **Test critical application workflows:**
  - [ ] Run smoke tests for all critical services
  - [ ] Verify database connectivity and transactions
  - [ ] Test API endpoints with real-world requests
  - [ ] Check async job processing (queues, cron jobs, etc.)

- [ ] **Storage validation:**
  - [ ] Verify all PersistentVolumes are accessible
  - [ ] Check storage class migrations completed successfully
  - [ ] Confirm no data corruption or access issues
  - [ ] Test read/write operations on volumes

- [ ] **Network & DNS validation:**
  - [ ] Verify DNS resolution for all services
  - [ ] Test external traffic ingestion
  - [ ] Confirm service-to-service communication
  - [ ] Check load balancer health (if applicable)

- [ ] **Observability & monitoring:**
  - [ ] Verify metrics are being collected (Prometheus, Cloud Monitoring, etc.)
  - [ ] Confirm logs are being shipped (Cloud Logging, Fluentd, etc.)
  - [ ] Check alert rules are firing correctly
  - [ ] Validate tracing/APM is functioning

### Phase 3: Feature & Configuration Validation (6-24 hours post-upgrade)

- [ ] **Validate new 1.30 features** (if adopting):
  - [ ] Test any new API versions you're planning to use
  - [ ] Verify feature gates are set as expected
  - [ ] Validate new scheduler behavior if relevant

- [ ] **Re-verify flow control (v1beta3 → v1 migration):**
  - [ ] Confirm FlowSchema objects are v1 and functioning
  - [ ] Check priority-and-fairness is working correctly
  - [ ] Validate API server request handling under load

- [ ] **Confirm static pod stability:**
  - [ ] Verify any static pods are running correctly
  - [ ] Check static pod logs for issues
  - [ ] Confirm kubelet configuration stability

- [ ] **Validate RBAC & security:**
  - [ ] Verify ClusterRole/ClusterRoleBinding configurations still work
  - [ ] Test service account tokens and authentication
  - [ ] Confirm Pod Security Policies or Pod Security Standards are enforced

### Phase 4: Performance Validation (6-24 hours post-upgrade)

- [ ] **Cluster performance baseline:**
  - [ ] Compare API latency with pre-upgrade baseline
  - [ ] Check node CPU and memory utilization
  - [ ] Monitor container startup times
  - [ ] Verify pod scheduling latency

- [ ] **Application performance:**
  - [ ] Confirm application response times are normal
  - [ ] Check database query performance
  - [ ] Verify no unexpected resource consumption
  - [ ] Validate throughput/RPS metrics

- [ ] **Review upgrade-related metrics:**
  - [ ] Check peak node allocation during surge upgrade
  - [ ] Monitor for any lingering resource pressure
  - [ ] Verify container image pull rates normalized

---

## Post-Upgrade Checklist - Dev Clusters (Rapid Channel)

- [ ] **Document findings** from dev cluster upgrades
- [ ] **Share lessons learned** with team before prod upgrades
- [ ] **Identify any production-impacting issues** from dev experience
- [ ] **Validate all test workloads** continue to function correctly

---

## Post-Upgrade Checklist - Prod Clusters (Stable Channel)

- [ ] **Prioritize post-upgrade validation** - assign dedicated staff
- [ ] **Monitor error rates** in production for 24 hours:
  - [ ] 5xx error rates
  - [ ] Timeout rates
  - [ ] Dependency errors

- [ ] **Customer/stakeholder communication:**
  - [ ] Notify teams that upgrade completed successfully
  - [ ] Document any observed issues or workarounds
  - [ ] Share post-upgrade status report

- [ ] **Extended monitoring:**
  - [ ] Continue elevated monitoring for 48-72 hours post-upgrade
  - [ ] Maintain increased on-call coverage
  - [ ] Prepare rollback procedures in case critical issues emerge

---

## Rollback & Troubleshooting

### Important: Auto-Upgrade Cannot Be Rolled Back

Since Autopilot clusters auto-upgrade and you cannot disable automatic upgrades, understand that:
- **Control plane downgrade** is not typically supported
- **Node downgrade** requires manual node pool recreation
- Plan mitigation strategies before upgrade, not rollback strategies

### If Issues Arise Post-Upgrade

- [ ] **Identify root cause** using cluster logs, events, and metrics
- [ ] **Escalate to Google Cloud Support** if:
  - Critical application failures
  - Data loss or corruption suspected
  - Cluster control plane instability
  - Unable to schedule or run pods

- [ ] **Implement workarounds** while investigating:
  - Cordon affected nodes if safe
  - Scale up unaffected node pools
  - Redirect traffic away from affected clusters

---

## Deprecated APIs Reference (1.29 → 1.30)

### Critical Removals in 1.30

| Deprecated API | Removal | Migration Path |
|---|---|---|
| `flowcontrol.apiserver.k8s.io/v1beta3` | Removed in 1.30 | Migrate to `flowcontrol.apiserver.k8s.io/v1` (available since 1.29) |
| Storage classes: `4k`, `8k`, `16k`, `v1-dynamic-40` | Removed in 1.30 | Migrate to v2 storage classes (available since 1.26) |

**Action:** Audit all clusters immediately for these resources and migrate before the upgrade window.

---

## Key Contacts & Escalation

- **Google Cloud Support:** [File ticket for any blockers](https://cloud.google.com/support)
- **Team Lead:** [Insert your escalation contact]
- **On-Call Engineer:** [Insert on-call contact]
- **Communications Lead:** [Insert for customer updates]

---

## Sign-Off & Timeline

### Checklist Owner
- **Name:** _______________
- **Email:** _______________
- **Date Completed:** _______________

### Pre-Upgrade Sign-Off
- [ ] All pre-upgrade items completed
- [ ] No blocking issues identified
- [ ] Stakeholders notified and ready
- **Signed off by:** _______________ **Date:** _______________

### Post-Upgrade Sign-Off
- [ ] All post-upgrade validation complete
- [ ] No critical issues remain
- [ ] Normal operations resumed
- **Signed off by:** _______________ **Date:** _______________

---

## Additional Resources

- [GKE Autopilot Cluster Upgrades](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot)
- [GKE Best Practices for Upgrading Clusters](https://cloud.google.com/kubernetes-engine/docs/best-practices/upgrading-clusters)
- [GKE Feature and API Deprecations](https://cloud.google.com/kubernetes-engine/docs/deprecations)
- [Kubernetes Deprecation Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/)
- [GKE Release Notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)

---

**Last Updated:** March 18, 2026
**Version:** 1.0
