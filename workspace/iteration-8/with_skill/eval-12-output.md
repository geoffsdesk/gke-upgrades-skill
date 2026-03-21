# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Istio service mesh adds complexity to GKE upgrades, but following the correct sequence and validation steps minimizes risk. The key is **control plane first, Istio compatibility validation, then gradual node pool upgrades** with careful mesh health monitoring.

## Upgrade Sequence

### Phase 1: GKE Control Plane (Low Risk)
```bash
# 1. Upgrade GKE control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# 2. Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should still show 1.31 nodes
```

**Why control plane first:** Istio control plane pods run as regular workloads and aren't affected by GKE control plane upgrades. The mesh continues operating normally.

### Phase 2: Istio Compatibility Validation
```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio supports Kubernetes 1.32
# Check: https://istio.io/latest/docs/releases/supported-releases/
```

**Compatibility matrix:** Istio typically supports N-2 Kubernetes versions. If your Istio is more than 2 minor versions behind K8s 1.32, upgrade Istio first before proceeding to node pools.

### Phase 3: Node Pool Upgrade Strategy

**Recommended: Gradual rolling upgrade with mesh validation**

```bash
# Configure conservative surge settings for mesh workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade one node pool at a time
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Why conservative surge:** Istio sidecars need time to gracefully terminate connections and drain traffic. Fast parallel upgrades can cause connection drops.

## Istio-Specific Risks & Mitigations

### 1. Sidecar Injection During Pod Recreation
**Risk:** Pods recreated on new nodes may get different sidecar versions or injection failures.

**Mitigation:**
```bash
# Verify injection webhook is healthy before upgrading
kubectl get validatingwebhookconfigurations istio-validator-istio-system
kubectl get mutatingwebhookconfigurations istio-sidecar-injector-istio-system

# Check sidecar injection working on new nodes
kubectl run test-pod --image=nginx --labels="app=test" -n NAMESPACE
kubectl get pod test-pod -o yaml | grep -A 5 -B 5 istio-proxy
kubectl delete pod test-pod
```

### 2. Traffic Disruption During Node Drain
**Risk:** Envoy sidecars may not gracefully handle connection draining during node eviction.

**Mitigation:**
```bash
# Increase termination grace period for meshed workloads
# In your Deployment spec:
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 60  # Default 30 may be too short
```

### 3. Service Discovery Issues
**Risk:** Istio's service discovery may temporarily lose endpoints during node transitions.

**Mitigation:**
```bash
# Monitor endpoint health during upgrade
kubectl get endpoints -A | grep -v "ENDPOINTS"
kubectl get pods -n istio-system -l app=istiod  # Ensure discovery healthy
```

### 4. mTLS Certificate Rotation Issues
**Risk:** Pod restarts may trigger certificate rotation at scale, overwhelming the CA.

**Mitigation:**
```bash
# Monitor Citadel/istiod logs for certificate errors
kubectl logs -n istio-system -l app=istiod | grep -i cert

# Check for certificate renewal errors
kubectl get pods -A | grep -i tls
```

## Pre-Upgrade Checklist

```markdown
GKE + Istio Pre-Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.31.x | Target: 1.32.x
- [ ] Current Istio version: ___ | K8s 1.32 compatibility confirmed

Istio Health Baseline
- [ ] Istio control plane pods healthy: `kubectl get pods -n istio-system`
- [ ] Proxy injection working: test pod injection in dev namespace
- [ ] mTLS working: `istioctl authn tls-check POD_NAME.NAMESPACE.svc.cluster.local`
- [ ] Traffic metrics flowing: check Kiali/Grafana dashboards
- [ ] No certificate errors in istiod logs

Workload Readiness
- [ ] PDBs configured for critical meshed services
- [ ] terminationGracePeriodSeconds ≥ 60s for meshed workloads
- [ ] Service dependencies mapped (which services call which)
- [ ] Traffic shaping policies documented (DestinationRules, VirtualServices)

Infrastructure
- [ ] Conservative surge settings: maxSurge=1, maxUnavailable=0
- [ ] Upgrade plan: control plane → validation → node pools one at a time
- [ ] Rollback plan: have previous Istio config backed up
```

## Validation Commands During Upgrade

**After control plane upgrade:**
```bash
# Istio should be unaffected
kubectl get pods -n istio-system
istioctl proxy-status  # All proxies should be SYNCED
```

**During node pool upgrade:**
```bash
# Monitor mesh connectivity
kubectl exec -n NAMESPACE POD_NAME -c istio-proxy -- \
  curl -s http://localhost:15000/clusters | grep healthy

# Check for proxy errors
kubectl logs -n NAMESPACE POD_NAME -c istio-proxy | tail -20

# Verify service mesh traffic
istioctl proxy-status
kubectl get vs,dr,gw -A  # VirtualServices, DestinationRules, Gateways
```

**Continuous monitoring:**
```bash
# Watch for pods stuck in terminating (proxy drain issues)
watch 'kubectl get pods -A | grep Terminating'

# Monitor endpoint churn
watch 'kubectl get endpoints -A | wc -l'
```

## Post-Upgrade Validation Checklist

```markdown
Post-Upgrade Validation
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] All proxies connected: `istioctl proxy-status` (no STALE_ENDPOINTS)
- [ ] mTLS working: `istioctl authn tls-check SERVICE.NAMESPACE.svc.cluster.local`
- [ ] Traffic flowing: check service-to-service calls in applications
- [ ] Metrics collection: verify Prometheus scraping sidecar metrics
- [ ] Ingress/egress gateways functional
- [ ] No certificate errors in istiod logs
- [ ] Application smoke tests passing through mesh
```

## Rollback Strategy

**If mesh breaks during node upgrade:**

1. **Stop the upgrade** (if in progress):
   ```bash
   # GKE will finish current node batch, then stop
   ```

2. **Restore service immediately:**
   ```bash
   # Option 1: Cordon new nodes, force pods back to old nodes
   kubectl cordon -l kubernetes.io/os=linux  # Assuming new nodes
   kubectl delete pods -n NAMESPACE -l app=PROBLEM_APP
   
   # Option 2: Temporarily disable sidecar injection
   kubectl label namespace NAMESPACE istio-injection-
   kubectl rollout restart deployment/APP_NAME -n NAMESPACE
   ```

3. **Create rollback node pool** (if needed):
   ```bash
   gcloud container node-pools create rollback-pool \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.31.x-gke.previous \
     --num-nodes 3
   ```

## Common Istio + GKE Upgrade Issues

| Issue | Symptoms | Fix |
|-------|----------|-----|
| **Sidecar injection fails** | New pods missing istio-proxy container | Check webhook configs, restart istiod |
| **Traffic 503 errors** | Intermittent connection failures | Increase terminationGracePeriodSeconds |
| **Certificate rotation storm** | Mass cert renewal, istiod CPU spike | Stagger pod restarts, scale istiod |
| **Service discovery lag** | Endpoints empty/stale | Wait for endpoints to populate, restart istiod if stuck |
| **Ingress gateway down** | External traffic failing | Check gateway pod node assignment, PDBs |

## Advanced: Multi-Cluster Mesh Considerations

If running Istio multi-cluster:
1. Upgrade **one cluster at a time** with full validation between clusters
2. Monitor cross-cluster service discovery (`istioctl proxy-config endpoints`)  
3. Verify cross-cluster mTLS certificates are valid
4. Test failover behavior during upgrade windows

---

**Key Success Factors:**
- Go slow: control plane → validate → node pools one by one
- Monitor mesh health continuously during upgrade
- Have rollback plan ready
- Test in staging with identical Istio setup first

This gradual approach turns a potentially risky operation into a manageable, observable process. The mesh adds complexity, but following this sequence keeps your services available throughout the upgrade.