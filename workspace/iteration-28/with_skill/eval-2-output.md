# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) + 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (minor version)  
**Timeline:** Auto-upgrade scheduled next month

## Pre-Upgrade Checklist

### Version & Channel Readiness
- [ ] **Dev clusters already on 1.32:** Verify dev clusters upgraded successfully on Rapid channel
  ```bash
  gcloud container clusters describe DEV_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"
  gcloud container clusters describe DEV_CLUSTER_2 --region REGION --format="value(currentMasterVersion)"
  ```
- [ ] **Prod clusters still on 1.31:** Confirm current version before auto-upgrade
  ```bash
  gcloud container clusters describe PROD_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"
  gcloud container clusters describe PROD_CLUSTER_2 --region REGION --format="value(currentMasterVersion)"
  ```
- [ ] **1.32 available in Stable channel:** Verify target version is ready for auto-upgrade
  ```bash
  gcloud container get-server-config --region REGION --format="yaml(channels.STABLE)"
  ```

### Compatibility Assessment
- [ ] **GKE 1.32 release notes reviewed** for breaking changes and deprecations
- [ ] **Deprecated API usage check** (critical for minor upgrades):
  ```bash
  # Check each cluster
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```
- [ ] **GKE deprecation insights reviewed** in console (Insights tab → "Deprecations and Issues")
- [ ] **Third-party operators compatible with K8s 1.32:**
  - [ ] Service mesh (Istio/ASM) version supports 1.32
  - [ ] cert-manager version supports 1.32  
  - [ ] Monitoring operators (Prometheus, etc.) support 1.32
  - [ ] Custom admission webhooks tested against 1.32 APIs

### Workload Readiness (Autopilot-specific)
- [ ] **All containers have resource requests** (mandatory in Autopilot):
  ```bash
  # Check for missing requests
  kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[]?.resources.requests == null) | {ns:.metadata.namespace, name:.metadata.name}'
  ```
- [ ] **No bare pods** — all workloads managed by controllers (Deployments, StatefulSets, etc.)
- [ ] **PDBs configured** for critical workloads but not overly restrictive:
  ```bash
  kubectl get pdb -A -o wide
  # Verify ALLOWED DISRUPTIONS > 0 for each PDB
  ```
- [ ] **terminationGracePeriodSeconds ≤ 600s** (Autopilot limit for most pods, 25s for Spot)
- [ ] **StatefulSet data backed up** with application-level snapshots (if applicable)

### Lessons from Dev Environment
- [ ] **Dev cluster upgrade outcomes documented:**
  - [ ] Any pod creation failures post-upgrade?
  - [ ] Admission webhook issues encountered?
  - [ ] Performance changes observed?
  - [ ] HPA/VPA behavior changes?
- [ ] **Dev environment smoke tests passed** on 1.32
- [ ] **Known issues from dev identified and mitigated**

### Maintenance Window Planning
- [ ] **Maintenance windows configured** for off-peak hours on prod clusters:
  ```bash
  gcloud container clusters update PROD_CLUSTER --region REGION \
    --maintenance-window-start "2024-02-03T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  ```
- [ ] **Upgrade sequence planned:** Prod cluster 1 → validate → Prod cluster 2
- [ ] **"No upgrades" exclusion ready** if emergency deferral needed (30-day max):
  ```bash
  # Keep this command ready but don't run unless deferral needed
  gcloud container clusters update PROD_CLUSTER --region REGION \
    --add-maintenance-exclusion-name="emergency-defer" \
    --add-maintenance-exclusion-start="2024-01-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-02-14T00:00:00Z" \
    --add-maintenance-exclusion-scope=no_upgrades
  ```

### Operations Readiness
- [ ] **Monitoring baseline captured** (error rates, latency, throughput)
- [ ] **72h scheduled upgrade notifications** enabled (if available in your region):
  ```bash
  gcloud container clusters update PROD_CLUSTER --region REGION --enable-scheduled-upgrades
  ```
- [ ] **Upgrade timeline communicated** to stakeholders
- [ ] **On-call rotation aware** of planned auto-upgrade window
- [ ] **Rollback plan documented** (limited options in Autopilot — mainly workload-level rollback)

---

## Post-Upgrade Checklist

### Control Plane Health (Per Cluster)
- [ ] **Control plane at 1.32:**
  ```bash
  gcloud container clusters describe PROD_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"
  gcloud container clusters describe PROD_CLUSTER_2 --region REGION --format="value(currentMasterVersion)"
  ```
- [ ] **System pods healthy:**
  ```bash
  kubectl get pods -n kube-system --context=PROD_CLUSTER_1
  kubectl get pods -n kube-system --context=PROD_CLUSTER_2
  ```
- [ ] **All nodes Ready** (Autopilot manages node upgrades automatically):
  ```bash
  kubectl get nodes --context=PROD_CLUSTER_1
  kubectl get nodes --context=PROD_CLUSTER_2
  ```

### Workload Health Validation
- [ ] **No stuck pods:**
  ```bash
  kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --context=PROD_CLUSTER_1
  kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --context=PROD_CLUSTER_2
  ```
- [ ] **All deployments at desired replica count:**
  ```bash
  kubectl get deployments -A --context=PROD_CLUSTER_1
  kubectl get deployments -A --context=PROD_CLUSTER_2
  ```
- [ ] **StatefulSets fully ready:**
  ```bash
  kubectl get statefulsets -A --context=PROD_CLUSTER_1
  kubectl get statefulsets -A --context=PROD_CLUSTER_2
  ```
- [ ] **No PDB violations** during upgrade (check Cloud Logging)
- [ ] **Ingress/load balancers responding** correctly

### API and Webhook Functionality
- [ ] **No admission webhook failures:**
  ```bash
  kubectl get events -A --field-selector type=Warning | grep webhook
  ```
- [ ] **HPA/VPA operating normally:**
  ```bash
  kubectl get hpa -A --context=PROD_CLUSTER_1
  kubectl describe hpa -A --context=PROD_CLUSTER_1 | grep -A5 "Scaling\|Events"
  ```
- [ ] **Test pod creation works:**
  ```bash
  kubectl run test-pod --image=nginx --rm -it --restart=Never --context=PROD_CLUSTER_1 -- echo "API test"
  kubectl run test-pod --image=nginx --rm -it --restart=Never --context=PROD_CLUSTER_2 -- echo "API test"
  ```

### Performance & Observability
- [ ] **Metrics pipeline active** — no collection gaps
- [ ] **Application logs flowing** to aggregation (Cloud Logging, etc.)
- [ ] **Error rates within baseline** (compare to pre-upgrade metrics)
- [ ] **Latency within baseline** (p50/p95/p99 from load balancers/APM)
- [ ] **Resource utilization normal** — no unexpected CPU/memory spikes

### Final Validation
- [ ] **Smoke tests passed** on both prod clusters
- [ ] **User-facing functionality verified** 
- [ ] **Auto-upgrade success documented** in runbook/changelog
- [ ] **Lessons learned captured** for future upgrades
- [ ] **Next upgrade timeline reviewed** (1.33 will arrive in Stable ~1 month after Regular)

---

## Emergency Procedures

**If prod auto-upgrade fails or causes issues:**

1. **Check GKE operations status:**
   ```bash
   gcloud container operations list --region REGION --filter="targetLink:CLUSTER_NAME"
   ```

2. **Apply temporary "no upgrades" exclusion** to prevent additional auto-upgrades:
   ```bash
   gcloud container clusters update PROD_CLUSTER --region REGION \
     --add-maintenance-exclusion-name="incident-response" \
     --add-maintenance-exclusion-start="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     --add-maintenance-exclusion-end="$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
     --add-maintenance-exclusion-scope=no_upgrades
   ```

3. **Review troubleshooting in order:**
   - Admission webhook failures (most common with 1.31→1.32)
   - Missing resource requests blocking pod creation
   - PDB over-protection causing drain issues
   - System component compatibility (coredns, metrics-server)

**Key insight for your setup:** Since your dev clusters on Rapid channel will upgrade to 1.32 weeks before your prod clusters on Stable, you have a natural testing window. Use that time to validate your workloads and catch any 1.32-specific issues before they hit production.