# Istio Service Mesh + GKE 1.31→1.32 Upgrade Plan

Service mesh upgrades require careful sequencing to avoid breaking inter-service communication. Here's the battle-tested approach for Istio on GKE.

## Executive Summary

**Correct order:** Upgrade Istio control plane first, then GKE cluster, then Istio data plane (sidecars). This maintains compatibility throughout the process and minimizes service disruption.

## Pre-flight Checks

```markdown
Istio + GKE Compatibility Check
- [ ] Current Istio version: ___ (check with `istioctl version`)
- [ ] Target Istio version supports Kubernetes 1.32 ([Istio support matrix](https://istio.io/latest/docs/releases/supported-releases/))
- [ ] Current GKE: 1.31 | Target GKE: 1.32
- [ ] Istio installation method: istioctl / Helm / Operator / ASM
- [ ] Mesh configuration: single-cluster / multi-cluster
- [ ] Gateway controllers identified (Istio Gateway / GKE Gateway API)
```

## Step-by-Step Upgrade Order

### Phase 1: Upgrade Istio Control Plane (FIRST)

**Why first:** Istio control planes are backward-compatible with older sidecars, but older control planes may not support newer Kubernetes APIs introduced in 1.32.

```bash
# Check current Istio version and Kubernetes compatibility
istioctl version
istioctl experimental precheck

# Upgrade Istio control plane to version compatible with K8s 1.32
# Example for istioctl installation:
istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false

# For ASM (Anthos Service Mesh), follow ASM upgrade guide
# ASM has specific GKE version requirements - verify compatibility first

# Verify control plane health
kubectl get pods -n istio-system
istioctl proxy-status
```

**Validation checkpoints:**
```bash
# All control plane pods running
kubectl get pods -n istio-system -o wide

# Envoy proxies connecting to new control plane
istioctl proxy-status | grep -v SYNCED

# No CRD issues
kubectl get crd | grep istio
```

### Phase 2: Upgrade GKE Cluster (SECOND)

**Standard cluster upgrade sequence:**

```bash
# 1. Control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Wait ~10-15 minutes, verify
kubectl get nodes
kubectl get pods -n istio-system

# 2. Node pool upgrade with conservative surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Critical mesh-specific monitoring during node upgrades:**
```bash
# Watch for admission webhook failures
kubectl get events -A --field-selector type=Warning | grep webhook

# Monitor Istio proxy status during node drain/replacement
watch 'istioctl proxy-status | head -20'

# Check for certificate renewal issues
kubectl get secrets -n istio-system | grep cacerts
```

### Phase 3: Upgrade Istio Data Plane/Sidecars (LAST)

**Sidecar upgrade strategies:**

**Option A - Rolling restart (recommended):**
```bash
# Restart deployments to pick up new sidecar version
kubectl rollout restart deployment -n NAMESPACE

# Or annotate for automatic sidecar injection update
kubectl patch deployment DEPLOYMENT_NAME -n NAMESPACE \
  -p '{"spec":{"template":{"metadata":{"annotations":{"kubectl.kubernetes.io/restartedAt":"'$(date -Iseconds)'"}}}}}'
```

**Option B - Canary sidecar upgrade:**
```bash
# Enable sidecar injection with new version on specific workloads
kubectl label namespace NAMESPACE istio-injection=enabled --overwrite
istioctl kube-inject -f deployment.yaml | kubectl apply -f -
```

## Service Mesh Specific Gotchas

### 1. Admission Webhook Compatibility
**Problem:** Istio's admission webhooks may reject pod creation after GKE CP upgrade if webhook certs are stale.

**Prevention:**
```bash
# Before GKE upgrade, check webhook health
kubectl get validatingwebhookconfigurations | grep istio
kubectl describe validatingwebhookconfigurations istio-validator-istio-system

# Verify webhook can reach API server
kubectl get events -n istio-system | grep webhook
```

**Fix if broken:**
```bash
# Temporary bypass (use carefully)
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"validation.istio.io","failurePolicy":"Ignore"}]}'

# Restart Istio control plane to refresh certs
kubectl rollout restart deployment/istiod -n istio-system
```

### 2. Certificate Rotation During Node Replacement
**Problem:** Node replacement can break mTLS if certificates don't refresh properly.

**Monitor:**
```bash
# Check for cert-related errors
kubectl logs -n istio-system -l app=istiod | grep -i cert

# Verify proxy cert status
istioctl proxy-config secret POD_NAME -n NAMESPACE
```

### 3. Gateway Controller Version Skew
**Problem:** Istio Gateways may fail if gateway controller and data plane versions drift.

**Check:**
```bash
# Verify gateway pods are healthy
kubectl get pods -n istio-system -l istio=ingressgateway
kubectl get pods -n istio-system -l istio=egressgateway

# Check gateway configuration
istioctl analyze -n istio-system
```

### 4. Multi-cluster Mesh Considerations
**If running multi-cluster mesh:**

```bash
# Upgrade primary cluster first, then remote clusters
# Verify cross-cluster connectivity after each cluster upgrade
istioctl proxy-config endpoints POD_NAME -n NAMESPACE | grep "HEALTHY"

# Check cross-cluster service discovery
kubectl get serviceentries -A
```

## Troubleshooting Common Failures

### Pods fail to start with "admission webhook rejected"
```bash
# Check webhook status
kubectl get validatingwebhookconfigurations istio-validator-istio-system -o yaml

# Restart Istio control plane
kubectl rollout restart deployment/istiod -n istio-system
```

### Sidecar injection stops working
```bash
# Verify injection configuration
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml

# Check namespace labels
kubectl get namespace NAMESPACE -o yaml | grep istio-injection
```

### Inter-service communication breaks
```bash
# Check DestinationRules and VirtualServices
istioctl analyze -A

# Verify Envoy configuration
istioctl proxy-config cluster POD_NAME -n NAMESPACE
istioctl proxy-config listener POD_NAME -n NAMESPACE
```

### mTLS certificate errors
```bash
# Check certificate chain
istioctl authn tls-check POD_NAME -n NAMESPACE

# Restart affected workloads to refresh certs
kubectl rollout restart deployment/DEPLOYMENT_NAME -n NAMESPACE
```

## Validation Checklist

```markdown
Post-Upgrade Validation
- [ ] GKE cluster at 1.32: `kubectl version --short`
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] All proxies connected: `istioctl proxy-status | grep -v SYNCED`
- [ ] No webhook failures: `kubectl get events -A | grep -i webhook | grep -i failed`
- [ ] Gateway traffic flowing: test ingress endpoints
- [ ] Inter-service mTLS working: `istioctl authn tls-check`
- [ ] Kiali/observability dashboards functional
- [ ] Distributed tracing working (Jaeger/Zipkin)
- [ ] Service-to-service latency within baseline
```

## Rollback Plan

**If things go wrong:**

1. **Sidecar issues:** Restart individual deployments to refresh sidecars
2. **Control plane issues:** Roll back Istio control plane version (if supported by your installation method)
3. **Severe service disruption:** Disable Istio injection temporarily:
   ```bash
   kubectl label namespace NAMESPACE istio-injection-
   kubectl rollout restart deployment -n NAMESPACE
   ```
4. **GKE rollback:** Node pools can be downgraded, but control plane rollback requires GKE support involvement

## Best Practices for Future Mesh + K8s Upgrades

- **Always test in staging first** with identical Istio configuration
- **Upgrade during maintenance windows** when traffic is lowest  
- **Have circuit breakers ready** to bypass mesh if needed
- **Monitor golden signals** (latency, errors, saturation) throughout
- **Keep Istio versions current** — don't let control plane lag too far behind K8s
- **Document your specific mesh configuration** — gateway setup, security policies, traffic routing rules

The key insight: **Istio control plane upgrade compatibility is more forgiving going forward (newer CP + older sidecars) than backward (older CP + newer K8s APIs)**. This is why we always upgrade Istio first.