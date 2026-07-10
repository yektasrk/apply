# Reason Taxonomy & Skill Vocabulary

Shared definitions for classifying triage reasons. Hand these to every classifier
subagent verbatim so batches stay consistent.

## Candidate baseline

Site Reliability / Platform Engineer. Resume-verified strengths ONLY (do not
assume anything not on the resume): Kubernetes, Docker, Nomad; Ansible-based
Infrastructure-as-Code (Ansible + Vagrant + Argo CD) — **no Terraform**; CI/CD
pipelines; observability (Prometheus, Elastic Stack, Sentry, SLI/SLO); data
systems (Kafka, Hadoop/HDFS/YARN/ZooKeeper, PostgreSQL, Redis, Druid); identity
(Active Directory, Keycloak, Kerberos); object storage (S3, MinIO) — **no public
cloud platform (AWS/Azure/GCP) experience**; Python and Go; incident response /
24-7 on-call. Based in Tehran, Iran — assume no EU/UK work authorization by
default, no security clearance, English (not German/French/Dutch) unless a source
says otherwise. Treat Terraform and any public cloud (AWS/Azure/GCP) as GAPS, not
strengths, even when a reason lists them in a required-stack sentence.

## Not-suitable primary categories (assign exactly one)

Structural — cannot be changed by learning:

- `language` — requires proficiency in a human language (German/French/Dutch/…)
  the resume doesn't show.
- `clearance` — requires security clearance, vetting (SC/BPSS/ESC/EDV), or
  citizenship.
- `work-authorization` — requires existing right-to-work / no visa sponsorship.
- `location-onsite` — requires on-site presence or relocation the candidate can't
  meet.

Fixable / partly fixable:

- `missing-skill-stack` — role centers on a specific technology/stack the resume
  lacks (AWS, Azure, GCP, SAP, PowerShell/Windows, MLOps, LLM/RAG,
  embedded/firmware, Backstage/IDP, a niche tool, …).
- `seniority-track` — level/track mismatch: too junior/internship, OR
  management/architecture/lead/sales track rather than hands-on IC SRE/platform.
- `domain-mismatch` — a different engineering discipline or job function entirely:
  civil/water infrastructure, physical networking/data-center hardware, Windows
  enterprise IT/helpdesk, ML/data engineering, support/account management, …

- `other` — fits none of the above.

Rule: pick the single most decisive blocker. If a hard language requirement and a
skill gap are both stated, `language` wins.

## missing_skills extraction (independent of category)

Populate with canonical technology names the reason says the resume LACKS, even
when the primary category is not `missing-skill-stack`. Exclude human languages
(they are the `language` category) and broad phrases ("SRE/platform",
"infrastructure", "DevOps"). Empty list if none.

## Canonical skill vocabulary (map synonyms to these)

AWS, Azure, GCP, Kubernetes, Terraform, Ansible, Docker, Python, Go, PowerShell,
Windows Server, SAP, MLOps, LLM/RAG, Embedded/Firmware, Data-center Networking,
Backstage/IDP, Rust, Ceph/Storage, .NET, Java, Proxmox, OpenStack, VMware,
Spark/Databricks, Kafka, Security/Compliance.

Synonym hints: k8s → Kubernetes; IaC (when named as Terraform) → Terraform;
GenAI / RAG / vector-database → LLM/RAG; Hyper-V → virtualization tool named.

## Suitable-reason extraction

- `matched_skills` — strengths the reason credits for the fit. Vocabulary:
  Kubernetes, Terraform, Ansible, Docker, CI/CD, Linux, Observability/Monitoring,
  Incident/On-call, Python, Go, Cloud, SLI/SLO, High Availability, Automation,
  Platform/DevEx, Puppet, Windows, Networking. Synonyms: postmortems/reliability →
  Incident/On-call; observability → Observability/Monitoring; IaC → Terraform.
- `noted_gaps` — skills flagged as a gap even though the job is suitable (e.g.
  "Azure is the main gap" → `["Azure"]`). Canonical tech names.
