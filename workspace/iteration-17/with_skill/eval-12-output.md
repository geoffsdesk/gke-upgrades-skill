# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Overview
Service mesh upgrades require careful sequencing to avoid breaking data plane connectivity. The key is upgrading the **control plane first** (both GKE and Istio), then the **data plane** (nodes + sidecars).

## Pre-Upgrade: Istio Version Compatibility

**Critical first step:** Verify your Istio version supports Kubernetes 1.32.

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check Istio support matrix
# Istio 1.20+ supports K8s 1.29-1.32
# Istio 1.19+ supports K8s 1.28-1.31
```

**If your Istio version doesn't support K8s 1.32:**
1. Upgrade Istio FIRST (before GKE upgrade)
2. Test data plane connectivity after Istio upgrade
3. Then proceed with GKE upgrade

## Recommended Upgrade Order

### Phase 1: Control Plane Upgrades
```bash
# 1. Upgrade GKE control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.XXXX

# Wait for completion (~10-15 min), then verify
kubectl get pods -n kube-system

# 2. Upgrade Istio control plane (if needed)
istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false
# Or via Helm/ASM depending on your installation method
```

### Phase 2: Data Plane Upgrades
```bash
# 3. Configure conservative node pool upgrade settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 4. Upgrade node pools one at a time
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.XXXX
```

## Service Mesh Specific Precautions

### 1. Webhook Compatibility (Most Common Failure)
Istio's admission webhooks may fail against the new K8s API version:

```bash
# Check webhook health before upgrade
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# Test webhook response
kubectl run test-injection --image=nginx --dry-run=server -o yaml
```

**If webhooks fail post-upgrade:**
```bash
# Temporary mitigation - set failurePolicy to Ignore
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'

# Then upgrade Istio to fix permanently
```

### 2. Sidecar Injection During Node Upgrades
**Key insight:** When nodes drain during upgrade, pods with sidecars get rescheduled. The injection webhook must be healthy or pod creation fails.

```bash
# Before starting node upgrades, verify injection works
kubectl label namespace default istio-injection=enabled
kubectl run injection-test --image=nginx --rm -it --restart=Never
# Should show 2 containers (app + istio-proxy)
```

### 3. mTLS Connectivity
Watch for certificate/mTLS issues as sidecars restart:

```bash
# Monitor proxy status during upgrades
istioctl proxy-status

# Check for mTLS errors
kubectl logs -l security.istio.io/tlsMode=istio -c istio-proxy | grep -i tls
```

### 4. Traffic Management Rules
Istio Gateway/VirtualService specs may need updates for K8s 1.32:

```bash
# Audit Istio CRDs for deprecated fields
kubectl get gateways,virtualservices,destinationrules -A -o yaml | grep -i deprecated
```

## Conservative Upgrade Strategy for Production

### Option 1: Staged Node Pool Upgrades (Recommended)
```bash
# Upgrade non-mesh workloads first (test pools, system pools)
gcloud container node-pools upgrade system-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32.0-gke.XXXX

# Then upgrade mesh workload pools with conservative settings
gcloud container node-pools update app-pool \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

gcloud container node-pools upgrade app-pool \
  --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.32.0-gke.XXXX
```

### Option 2: Blue-Green Node Pool Migration
For ultra-conservative approach:
```bash
# Create new node pool at 1.32
gcloud container node-pools create app-pool-132 \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.32.0-gke.XXXX \
  --machine-type n1-standard-4 --num-nodes 3

# Gradually migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=app-pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool when confident
gcloud container node-pools delete app-pool --cluster CLUSTER_NAME --zone ZONE
```

## Pre-Flight Checklist

```
Istio + GKE Upgrade Checklist
- [ ] Current Istio version: ___
- [ ] Istio supports K8s 1.32: Y/N
- [ ] Baseline connectivity tests captured
- [ ] Istio control plane health verified: `kubectl get pods -n istio-system`
- [ ] Admission webhooks responding: `kubectl get validatingwebhookconfigurations | grep istio`
- [ ] mTLS policy inventory: `kubectl get peerauthentications -A`
- [ ] Gateway/VirtualService configs audited for deprecated fields
- [ ] Traffic routing tests documented (which services talk to which)
- [ ] Rollback plan: can recreate node pool at 1.31 if needed
```

## Monitoring During Upgrade

```bash
# Watch for sidecar injection failures
kubectl get events -A --field-selector reason=FailedCreate

# Monitor Istio control plane
watch 'kubectl get pods -n istio-system'

# Check proxy connectivity
istioctl proxy-config cluster WORKLOAD_POD.NAMESPACE

# Watch service mesh traffic
kubectl logs -n istio-system deployment/istiod | grep -i error
```

## Rollback Strategy

**If things break:**

1. **Webhook issues:** Patch failurePolicy to "Ignore" (temporary)
2. **Control plane issues:** Downgrade Istio (if Istio was upgraded)
3. **Node issues:** Create new node pool at 1.31, migrate workloads back
4. **mTLS breaks:** Check DestinationRule configs, verify CA certificates

**Critical:** GKE control plane cannot be downgraded easily. Focus rollback on Istio control plane and node pools.

## Post-Upgrade Validation

```bash
# End-to-end connectivity test
kubectl run sleep --image=curlimages/curl --rm -it --restart=Never -- \
  curl -v http://productpage.default.svc.cluster.local:9080/

# Verify all proxies healthy
istioctl proxy-status | grep -v SYNCED

# Check certificate validity
kubectl exec WORKLOAD_POD -c istio-proxy -- openssl x509 -in /etc/ssl/certs/cert-chain.pem -text -noout
```

## ASM (Anthos Service Mesh) Specific Notes

If using Google-managed ASM:
- ASM control plane is managed by Google, but you control the data plane upgrade timing
- ASM release channels align with GKE - check ASM compatibility matrix
- Use `asmcli` for ASM upgrades instead of `istioctl`

This plan prioritizes safety over speed. The conservative surge settings (`maxSurge=1`) will make upgrades slower but dramatically reduce the blast radius if issues occur.