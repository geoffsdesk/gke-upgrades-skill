# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Istio mesh upgrades require careful orchestration with GKE upgrades. The key is **control plane first, validate, then nodes** — with Istio validation at each step. Most "horror stories" come from skipping validation or upgrading everything simultaneously.

## Pre-Flight: Istio Compatibility Check

First, verify Istio-GKE version compatibility:

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check Istio control plane health
istioctl proxy-status
istioctl analyze -A
```

**Compatibility matrix:** Istio has specific GKE version support windows. For GKE 1.32, you'll need:
- **Istio 1.20+** (recommended: latest 1.21.x or 1.22.x)
- Check the [Istio-GKE compatibility matrix](https://istio.io/latest/docs/setup/platform-setup/gke/)

**Pre-upgrade Istio health baseline:**
```bash
# Capture current state
istioctl proxy-config cluster istiod-xxx-xxx.istio-system > pre-upgrade-cluster-config.txt
kubectl get pods -n istio-system -o wide > pre-upgrade-istio-pods.txt
kubectl get gateways,virtualservices,destinationrules -A > pre-upgrade-mesh-config.txt

# Test service-to-service connectivity
kubectl exec -n NAMESPACE POD_NAME -- curl -s http://SERVICE_NAME:PORT/health
```

## Upgrade Order: Control Plane → Nodes → Istio

### Step 1: GKE Control Plane Upgrade

```bash
# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Wait and verify (~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Validation after CP upgrade:**
```bash
# Istio control plane should still be healthy
kubectl get pods -n istio-system
istioctl proxy-status
istioctl analyze -A

# Test one service-to-service call
kubectl exec -n NAMESPACE POD_NAME -- curl -s http://SERVICE_NAME:PORT/health
```

⚠️ **Stop here if Istio shows any issues.** Control plane upgrade can occasionally break Istio's webhook configurations or API server connectivity.

### Step 2: Node Pool Upgrades (Conservative Surge)

For Istio, use conservative surge settings — mesh components are sensitive to rapid node churn:

```bash
# Configure conservative surge (Istio workloads need graceful migration)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Monitor during node upgrade:**
```bash
# Watch Istio pods reschedule gracefully
watch 'kubectl get pods -n istio-system -o wide'

# Monitor service mesh connectivity during migration
while true; do
  kubectl exec -n NAMESPACE POD_NAME -- curl -s http://SERVICE_NAME:PORT/health || echo "FAILED"
  sleep 30
done
```

### Step 3: Post-Upgrade Istio Validation

```bash
# Full mesh health check
istioctl proxy-status | grep -v SYNCED
istioctl analyze -A

# Envoy version alignment
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].status.containerStatuses[0].image}'

# Test cross-namespace service calls
kubectl exec -n frontend POD -- curl -s http://backend.backend-ns:8080/api/health
kubectl exec -n backend POD -- curl -s http://database.data-ns:5432/health
```

## Istio-Specific Risks & Mitigations

### 1. Webhook Configuration Conflicts
**Risk:** GKE upgrade can modify admission webhook configurations that Istio depends on.

**Mitigation:**
```bash
# Before upgrade: backup webhook configs
kubectl get validatingwebhookconfigurations -o yaml > istio-webhooks-backup.yaml
kubectl get mutatingwebhookconfigurations -o yaml > istio-mutating-webhooks-backup.yaml

# After upgrade: verify Istio webhooks are intact
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio
```

### 2. Envoy Proxy Version Skew
**Risk:** New GKE nodes come with different base images that may affect Envoy sidecar behavior.

**Mitigation:**
```bash
# Force sidecar refresh on new nodes (rolling restart)
kubectl rollout restart deployment/APP_NAME -n NAMESPACE

# Verify Envoy versions are consistent across the mesh
kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="istio-proxy")].image}{"\n"}{end}'
```

### 3. Service Discovery Issues
**Risk:** DNS or service registry changes during node migration.

**Mitigation:**
```bash
# Test service discovery from multiple namespaces
for ns in frontend backend payments; do
  echo "Testing from $ns:"
  kubectl exec -n $ns deployment/app -- nslookup istio-pilot.istio-system.svc.cluster.local
done

# Check Istio's internal service registry
istioctl proxy-config endpoints istiod-xxx-xxx.istio-system | grep SERVICE_NAME
```

### 4. Gateway/Ingress Connectivity
**Risk:** Load balancer IP changes or ingress controller restart during upgrade.

**Mitigation:**
```bash
# Monitor ingress gateway status
kubectl get svc -n istio-system istio-ingressgateway -w

# Test external connectivity throughout upgrade
while true; do
  curl -s https://your-app.example.com/health || echo "External access failed at $(date)"
  sleep 60
done
```

## Pre-Upgrade Checklist (Istio-Specific)

```markdown
Istio + GKE Upgrade Checklist
- [ ] Current Istio version: ___ | Compatible with GKE 1.32: Y/N
- [ ] Istio health baseline captured (proxy-status, analyze, connectivity tests)
- [ ] Webhook configurations backed up
- [ ] Test service mesh connectivity established
- [ ] PDBs configured for Istio control plane components (istiod, gateways)
- [ ] Istio configuration backed up (gateways, virtual services, destination rules)
- [ ] Monitoring dashboard for service mesh metrics active
- [ ] Emergency contact for Istio expertise available

GKE Upgrade Settings
- [ ] Conservative surge settings: maxSurge=1, maxUnavailable=0
- [ ] Control plane upgrade first, nodes second
- [ ] Skip-level node pool upgrade (if applicable) evaluated
- [ ] Maintenance window during low-traffic period
```

## Troubleshooting Common Istio + GKE Issues

### Issue: Istio pods stuck in pending after node upgrade
```bash
# Check if Istio node selectors conflict with new node labels
kubectl describe pods -n istio-system | grep -A 10 "Events"

# Verify resource requests/limits compatible with new node pool
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### Issue: Service mesh connectivity broken
```bash
# Check if Envoy sidecars are healthy
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[?(@.name=="istio-proxy")].ready}{"\n"}{end}'

# Restart Istio control plane if needed
kubectl rollout restart deployment/istiod -n istio-system
```

### Issue: External traffic not reaching the mesh
```bash
# Check ingress gateway pods and service
kubectl get pods -n istio-system -l app=istio-ingressgateway
kubectl get svc -n istio-system istio-ingressgateway

# Verify load balancer status
kubectl describe svc -n istio-system istio-ingressgateway
```

## Rollback Strategy

If the upgrade breaks Istio:

1. **Immediate:** Cordon new nodes, direct traffic to old nodes
```bash
kubectl cordon -l cloud.google.com/gke-nodepool=NEW_POOL
```

2. **Service level:** Restart problematic applications on old nodes
```bash
kubectl patch deployment APP_NAME -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"OLD_POOL"}}}}}'
```

3. **Full rollback:** Create new node pool at GKE 1.31, migrate workloads
```bash
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.PREVIOUS
```

## Expected Timeline

- **Control plane upgrade:** 10-15 minutes
- **Node pool upgrade:** 2-4 hours (depending on cluster size, conservative surge settings)
- **Istio validation:** 30 minutes between each step
- **Total window:** Plan 4-6 hours for a medium cluster (50-200 nodes)

This conservative approach minimizes risk by validating mesh health at each step. The "horror stories" typically come from upgrading everything simultaneously without validation checkpoints.