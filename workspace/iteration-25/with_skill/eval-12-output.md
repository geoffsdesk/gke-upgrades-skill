# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful coordination between the GKE control plane, Istio control plane, and data plane components. Here's the safe upgrade sequence:

## Pre-Upgrade: Istio Version Compatibility Check

**Critical first step:** Verify your current Istio version supports Kubernetes 1.32:

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check Istio/Kubernetes compatibility matrix
# Istio 1.20+ supports K8s 1.32
# Istio 1.18-1.19 may have issues with K8s 1.32
```

**If your Istio version is < 1.20:** Upgrade Istio BEFORE upgrading GKE to avoid API compatibility issues.

## Recommended Upgrade Sequence

### Phase 1: Control Plane Upgrade (GKE)
1. **Upgrade GKE control plane first** — this is required before node pools
2. Istio control plane (istiod) should continue working on the new K8s control plane
3. **Monitor:** Istio control plane pods stay healthy during CP upgrade

### Phase 2: Node Pool Strategy (Standard cluster)
**Recommended:** Use **autoscaled blue-green** upgrade strategy for service mesh environments:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --standard-rollout-policy=batch-node-count=2,batch-soak-duration=300s
```

**Why blue-green for service mesh:**
- Preserves network topology during transition
- Allows validation of Istio sidecar injection on new nodes before full cutover
- Quick rollback if Envoy proxies have issues with new node kernel/OS

### Phase 3: Istio Data Plane Validation
After each batch of nodes upgrades:
```bash
# Verify sidecar injection working on new nodes
kubectl get pods -n PRODUCTION_NAMESPACE -o jsonpath='{.items[*].spec.containers[*].name}' | grep istio-proxy

# Check Envoy proxy connectivity
kubectl exec -n NAMESPACE POD_NAME -c istio-proxy -- pilot-agent request GET stats/ready

# Validate service mesh traffic flow
kubectl exec -n NAMESPACE POD_NAME -c istio-proxy -- pilot-agent request GET clusters | grep "healthy.*priority.*0"
```

## Critical Watch Points for Service Mesh

### 1. Admission Webhook Compatibility
**Most common failure mode:** Istio's admission webhooks fail after GKE CP upgrade.

```bash
# Check webhook health immediately after CP upgrade
kubectl get validatingwebhookconfigurations istio-validator -o yaml
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml

# Test pod creation in mesh namespace
kubectl run test-mesh --image=nginx -n MESH_NAMESPACE --rm -it --restart=Never -- echo "webhook test"
```

**If webhooks fail:**
```bash
# Temporary mitigation - set failure policy to Ignore
kubectl patch validatingwebhookconfigurations istio-validator \
  -p '{"webhooks":[{"name":"config.validation.istio.io","failurePolicy":"Ignore"}]}'

# Then restart istiod to refresh certificates
kubectl rollout restart deployment/istiod -n istio-system
```

### 2. Envoy Proxy Version Compatibility
Check that Istio's Envoy version supports the new node OS/kernel:

```bash
# After first batch of nodes upgrade
kubectl get pods -n istio-system -l app=istiod -o yaml | grep -A2 -B2 "PILOT_ENABLE_WORKLOAD_ENTRY\|EXTERNAL_ISTIOD"

# Verify Envoy can reach istiod from new nodes
kubectl exec -n NAMESPACE POD_ON_NEW_NODE -c istio-proxy -- curl -I istiod.istio-system:15010/ready
```

### 3. Network Policy Interactions
GKE 1.32 has updated NetworkPolicy handling that may affect service mesh traffic:

```bash
# Before upgrade: document current network policies
kubectl get networkpolicies -A -o yaml > networkpolicies-backup.yaml

# After upgrade: verify mesh traffic still flows
kubectl exec -n NAMESPACE SOURCE_POD -- curl -I DESTINATION_SERVICE
```

## Complete Runbook

### Pre-flight Checklist
```
- [ ] Istio version ≥ 1.20 (supports K8s 1.32)
- [ ] Current mesh health baseline captured
- [ ] Backup Istio configuration: `kubectl get istio -A -o yaml > istio-config-backup.yaml`
- [ ] Test environment upgraded first with same Istio/GKE versions
- [ ] Grafana/monitoring active for service mesh metrics
```

### Step-by-Step Commands

```bash
# 1. Capture baseline mesh health
kubectl get pods -n istio-system
istioctl proxy-status
istioctl analyze -A

# 2. Upgrade GKE control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.Y

# 3. Verify Istio control plane survived CP upgrade
kubectl get pods -n istio-system -w
istioctl version --remote

# 4. Configure autoscaled blue-green for node pools
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s

# 5. Upgrade first node pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# 6. Validate mesh on upgraded nodes (during soak period)
kubectl get pods -n PRODUCTION_NAMESPACE -o wide --sort-by=.spec.nodeName
# Find pods on new nodes and test:
kubectl exec -n NAMESPACE POD_ON_NEW_NODE -c istio-proxy -- pilot-agent request GET ready

# 7. Complete upgrade if validation passes
# Blue-green will complete automatically after soak period

# 8. Post-upgrade validation
istioctl proxy-status
kubectl get services -n istio-system
curl -I http://YOUR_MESH_GATEWAY/health
```

### Troubleshooting Service Mesh Issues

**If admission webhooks fail:**
```bash
# Check webhook certificate status
kubectl get secrets -n istio-system | grep cacerts
kubectl describe validatingwebhookconfigurations istio-validator

# Restart istiod to refresh webhook certificates
kubectl rollout restart deployment/istiod -n istio-system
kubectl rollout status deployment/istiod -n istio-system
```

**If sidecars stop injecting:**
```bash
# Check sidecar injector webhook
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml

# Verify namespace labels
kubectl get namespace NAMESPACE --show-labels

# Test injection manually
kubectl apply -f <(istioctl kube-inject -f your-deployment.yaml) -n NAMESPACE
```

**If inter-service communication breaks:**
```bash
# Check Envoy config distribution
istioctl proxy-config cluster POD_NAME -n NAMESPACE

# Verify mTLS certificates
istioctl proxy-config secret POD_NAME -n NAMESPACE

# Check for version skew in data plane
istioctl proxy-status | grep -v SYNCED
```

## Recovery Plan

If the service mesh breaks during upgrade:

1. **Immediate:** Use blue-green rollback to return to old nodes:
   ```bash
   # Uncordon blue (old) nodes if still available
   kubectl uncordon -l cloud.google.com/gke-nodepool=OLD_POOL
   ```

2. **If rollback impossible:** Restart Istio control plane:
   ```bash
   kubectl rollout restart deployment/istiod -n istio-system
   kubectl delete pods -n istio-system -l app=istio-proxy --wait=false
   ```

3. **Last resort:** Temporarily disable mesh injection:
   ```bash
   kubectl label namespace NAMESPACE istio-injection-
   kubectl rollout restart deployment/YOUR_APP -n NAMESPACE
   ```

## Key Success Metrics

Monitor these throughout the upgrade:
- **Istio control plane:** All istiod pods Ready
- **Data plane:** `istioctl proxy-status` shows all proxies SYNCED  
- **Traffic flow:** Service-to-service calls maintain <1% error rate increase
- **mTLS:** Certificate rotation continues working
- **Ingress gateway:** External traffic maintains availability

The blue-green strategy gives you a 30-minute soak period to validate these metrics before committing to the new nodes.