# GKE + Istio Upgrade Plan: 1.29 → 1.30

The key to safe mesh upgrades is **sequencing** and **compatibility verification**. Istio has specific requirements around Kubernetes version support, and the control plane/data plane upgrade order matters.

## Pre-Upgrade: Istio Compatibility Check

**Critical first step** — verify your Istio version supports Kubernetes 1.30:

```bash
# Check current Istio version
istioctl version

# Check Istio's Kubernetes compatibility matrix
# Visit: https://istio.io/latest/docs/releases/supported-releases/
```

**Istio 1.20+ supports K8s 1.30**. If you're on Istio <1.20, you **must upgrade Istio first** before touching GKE.

## Recommended Upgrade Sequence

```
1. Upgrade Istio control plane (if needed for K8s 1.30 support)
2. Upgrade GKE control plane to 1.30
3. Upgrade GKE node pools (with careful data plane handling)
4. Upgrade Istio data plane (sidecar proxies)
5. Validate end-to-end mesh functionality
```

## Detailed Runbook

### Phase 1: Istio Control Plane Upgrade (if needed)

```bash
# Pre-flight: backup Istio config
kubectl get istio-system -o yaml > istio-backup.yaml
kubectl get gateway,virtualservice,destinationrule -A -o yaml > istio-traffic-backup.yaml

# Check upgrade path (if upgrading Istio)
istioctl x precheck
istioctl analyze -A

# Canary upgrade (recommended for prod)
istioctl install --set revision=1-20-0 --set values.pilot.env.EXTERNAL_ISTIOD=false
# Validate control plane before proceeding
```

### Phase 2: GKE Control Plane Upgrade

```bash
# Verify Istio webhook configs won't block the upgrade
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.5-gke.1014001  # Use latest 1.30 patch

# Validate - Istio control plane should remain healthy
kubectl get pods -n istio-system
istioctl proxy-status
```

### Phase 3: Node Pool Upgrade Strategy

**Critical mesh consideration**: Envoy sidecars maintain connections during pod restart. Use **conservative surge settings** to minimize connection disruption:

```bash
# Configure conservative surge for mesh workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools one at a time
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.5-gke.1014001
```

**Monitor mesh health during node upgrades:**
```bash
# Watch for proxy connection issues
watch 'istioctl proxy-status | grep -v SYNCED'

# Monitor Envoy cluster health
kubectl logs -l app=istiod -n istio-system --tail=50 | grep -i error

# Check service mesh connectivity
kubectl exec -n NAMESPACE deployment/WORKLOAD -- curl -s http://target-service:8080/health
```

### Phase 4: Data Plane (Sidecar) Upgrade

**Automatic vs Manual**: If using automatic sidecar injection with `istio-proxy` image, sidecars will be updated as pods restart during the node upgrade. For **revision-based deployments**, you need to explicitly migrate:

```bash
# Check which workloads need sidecar updates
istioctl proxy-status | grep -v "1.20"  # Replace with your target Istio version

# Rolling restart to pick up new sidecars (if using automatic injection)
kubectl rollout restart deployment/APP_NAME -n NAMESPACE

# For revision-based: update namespace labels
kubectl label namespace NAMESPACE istio.io/rev=1-20-0 --overwrite
kubectl rollout restart deployment -n NAMESPACE
```

## Mesh-Specific Pre-Upgrade Checklist

```
Istio Compatibility & Config
- [ ] Istio version supports K8s 1.30 (check compatibility matrix)
- [ ] Istio control plane healthy: `istioctl proxy-status`
- [ ] No proxy configuration errors: `istioctl analyze -A`
- [ ] Gateway/VirtualService configs backed up
- [ ] mTLS policies documented (will be preserved)
- [ ] Custom EnvoyFilters compatible with target Envoy version
- [ ] Third-party Istio addons (Jaeger, Kiali) version compatibility confirmed

Workload Preparation
- [ ] PDBs configured for meshed workloads (especially ingress gateways)
- [ ] Circuit breakers and retry policies tuned for brief connection drops
- [ ] Health check endpoints configured (`/health`, `/ready`)
- [ ] Graceful shutdown handling (SIGTERM) in applications
- [ ] Load balancer health checks account for sidecar startup time

Infrastructure
- [ ] Ingress gateways have anti-affinity rules (spread across nodes)
- [ ] Sufficient surge capacity for gateway pods (they're stateful-ish)
- [ ] Istio system namespace excluded from aggressive PDBs
```

## What to Watch For (Common Mesh Upgrade Issues)

### 1. Webhook Certificate Rotation
Istio admission webhooks can block upgrades if certificates expire:
```bash
# Check webhook cert validity
kubectl get validatingwebhookconfigurations istiod-default-validator -o yaml | grep caBundle | base64 -d | openssl x509 -noout -dates
```

### 2. Gateway Pod Disruption
Ingress/egress gateways are particularly sensitive:
```bash
# Monitor gateway availability
kubectl get pods -n istio-system -l istio=ingressgateway -w
curl -I https://your-app.domain.com/health  # External health check
```

### 3. Sidecar Version Skew
Mixed Istio versions can cause issues:
```bash
# Ensure consistent versions after upgrade
istioctl proxy-status | awk '{print $8}' | sort | uniq -c
```

### 4. mTLS Certificate Issues
Rarely, certificate rotation during upgrades causes temporary auth failures:
```bash
# Check for mTLS errors
kubectl logs -l app=istiod -n istio-system | grep -i "certificate\|tls"
```

## Post-Upgrade Validation

```bash
# Control plane health
istioctl proxy-status | grep -v SYNCED  # Should be empty
kubectl get pods -n istio-system

# Data plane connectivity
istioctl analyze -A  # Should report no issues

# End-to-end mesh validation
kubectl exec -n NAMESPACE deployment/APP -- curl -s http://target.namespace:8080/health
# Check for proper mTLS (should see client certificates in logs)

# Performance baseline
# Compare pre/post upgrade: request latency, error rates, proxy CPU/memory
```

## Rollback Strategy

**Control plane**: Istio supports rollback to the previous revision
**Node pools**: Create new pools at K8s 1.29, migrate workloads, delete upgraded pools
**Data plane**: Revert namespace labels to previous Istio revision

The good news: Istio is generally **upgrade-resilient** once you get the sequencing right and verify version compatibility upfront. The mesh will maintain traffic flow even with brief sidecar restarts during node upgrades.