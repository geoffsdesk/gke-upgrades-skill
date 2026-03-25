# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful sequencing to avoid breaking inter-service communication. Here's your upgrade plan:

## Pre-Upgrade Assessment

First, determine your Istio deployment model:

```bash
# Check current Istio version and installation method
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check if using Google-managed Anthos Service Mesh (ASM) or self-managed Istio
gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(addonsConfig.serviceMeshConfig)"
```

**Critical compatibility check:** Verify your Istio version supports Kubernetes 1.32:
- **Istio 1.20+**: Supports K8s 1.32
- **Istio 1.18-1.19**: May have compatibility issues with K8s 1.32 API changes
- **ASM managed**: Google handles compatibility automatically

## Upgrade Sequence (Critical Order)

### Phase 1: Control Plane Upgrade
**Why first:** Istio control plane must be compatible with new K8s APIs before node upgrades begin draining sidecars.

1. **Upgrade Istio control plane BEFORE GKE control plane:**
   ```bash
   # For self-managed Istio (using istioctl)
   istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false
   
   # For ASM managed - enable auto-upgrade if not already
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --update-addons=ServiceMesh=ENABLED
   ```

2. **Verify Istio control plane health:**
   ```bash
   kubectl get pods -n istio-system
   kubectl logs -n istio-system -l app=istiod --tail=50
   istioctl proxy-status  # Should show all proxies SYNCED
   ```

3. **Upgrade GKE control plane to 1.32:**
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version 1.32.0-gke.XXXX
   ```

4. **Re-verify Istio after CP upgrade:**
   ```bash
   istioctl proxy-status
   kubectl get validatingwebhookconfigurations | grep istio
   ```

### Phase 2: Node Pool Preparation
**Before upgrading nodes:** Ensure admission webhooks won't break during pod recreation.

5. **Test webhook compatibility:**
   ```bash
   # Create test pod to verify admission webhooks work
   kubectl run istio-test --image=nginx --labels="app=test" --rm -it --restart=Never
   
   # Check sidecar injection working
   kubectl get pod istio-test -o yaml | grep -A 5 "istio-proxy"
   ```

6. **Configure conservative node pool upgrade settings:**
   ```bash
   # Slow, careful rolling update - let each node stabilize
   gcloud container node-pools update default-pool \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --max-surge-upgrade 1 \
     --max-unavailable-upgrade 0
   ```

### Phase 3: Node Pool Upgrade
**With mesh-aware PDBs and monitoring:**

7. **Set mesh-aware PDBs before upgrading nodes:**
   ```bash
   # Example for a service with 3 replicas
   kubectl apply -f - <<EOF
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: my-service-pdb
     namespace: my-namespace
   spec:
     minAvailable: 2  # Keep majority running during drain
     selector:
       matchLabels:
         app: my-service
   EOF
   ```

8. **Upgrade node pools one at a time:**
   ```bash
   gcloud container node-pools upgrade NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.32.0-gke.XXXX
   ```

9. **Monitor mesh health during upgrade:**
   ```bash
   # Watch for proxy sync issues
   watch 'istioctl proxy-status | grep -v SYNCED'
   
   # Monitor service-to-service connectivity
   kubectl get virtualservices,destinationrules -A
   
   # Check for certificate issues
   kubectl logs -n istio-system -l app=istiod | grep -i cert
   ```

## Mesh-Specific Failure Modes to Watch

### 1. Admission Webhook Failures
**Symptom:** Pods fail to create with "admission webhook rejected" errors after control plane upgrade.

**Fix:**
```bash
# Temporarily set webhook failure policy to Ignore
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'

# After nodes upgrade, restore to Fail
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Fail"}]}'
```

### 2. Sidecar Version Skew
**Symptom:** Newly created pods get newer Envoy sidecars that can't communicate with older ones still running.

**Prevention:** Use gradual rollout with PDBs to ensure service replicas upgrade together, not scattered across upgrade waves.

**Fix if it happens:**
```bash
# Force restart deployment to get consistent sidecar versions
kubectl rollout restart deployment/my-service -n my-namespace
```

### 3. Certificate Rotation Issues
**Symptom:** mTLS failures, connection refused between services after upgrade.

**Diagnosis:**
```bash
istioctl authn tls-check service1.namespace1.svc.cluster.local
kubectl exec deployment/service1 -c istio-proxy -- openssl s_client -connect service2.namespace2:8080 -verify_return_error
```

**Fix:**
```bash
# Restart istiod to refresh certificates
kubectl rollout restart deployment/istiod -n istio-system
```

## Pre-Upgrade Checklist

```
Service Mesh Upgrade Checklist
- [ ] Istio version compatibility with K8s 1.32 verified
- [ ] Istio control plane upgraded BEFORE GKE control plane  
- [ ] Webhook configurations tested (`kubectl run test-pod`)
- [ ] PDBs configured for critical mesh services (minAvailable: majority)
- [ ] Baseline metrics captured (success rates, latency, certificate expiry)
- [ ] Node upgrade strategy: maxSurge=1, maxUnavailable=0 (conservative)
- [ ] Service mesh monitoring active (`istioctl proxy-status`)
- [ ] Rollback plan: webhook failurePolicy patches, deployment restarts
```

## Post-Upgrade Validation

```bash
# All proxies synced with control plane
istioctl proxy-status | grep -v SYNCED  # Should be empty

# Service-to-service connectivity test
kubectl exec deployment/source-service -- curl http://target-service.namespace.svc.cluster.local:8080/health

# Certificate validity
istioctl proxy-config secret deployment/my-service.my-namespace | grep ACTIVE

# No webhook errors in recent events
kubectl get events -A --field-selector type=Warning | grep webhook
```

## If Things Go Wrong

**Immediate rollback steps:**
1. Set webhook failurePolicy to "Ignore" (pods can create without sidecars)
2. Restart affected deployments to get consistent sidecar versions
3. Check Istio control plane logs for specific errors
4. Consider temporarily disabling strict mTLS if connection issues persist

**The key insight:** Service mesh upgrades fail when the control plane and data plane (sidecars) become incompatible during the rolling upgrade. The careful sequencing above prevents this by ensuring Istio adapts to the new Kubernetes version before any sidecars are recreated on new nodes.

Would you like me to adapt this plan for your specific Istio version or deployment model (ASM vs. self-managed)?