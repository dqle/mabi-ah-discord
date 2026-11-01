{{/*
Expand the name of the chart.
*/}}
{{- define "mabi-ah-discord.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "mabi-ah-discord.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "mabi-ah-discord.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "mabi-ah-discord.labels" -}}
helm.sh/chart: {{ include "mabi-ah-discord.chart" . }}
{{ include "mabi-ah-discord.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "mabi-ah-discord.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mabi-ah-discord.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "mabi-ah-discord.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "mabi-ah-discord.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "helpers.list-env-variables"}}
{{- $root := . }}
{{- range $key, $val := .Values.env }}
{{- if $val }}
- name: {{ $key }}
  valueFrom:
    secretKeyRef:
      name: {{ include "mabi-ah-discord.fullname" $root }}
      key: {{ $key }}
{{- end }}
{{- end }}
{{- end }}