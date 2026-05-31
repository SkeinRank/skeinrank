{{- define "skeinrank.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "skeinrank.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "skeinrank.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "skeinrank.labels" -}}
helm.sh/chart: {{ include "skeinrank.chart" . }}
app.kubernetes.io/name: {{ include "skeinrank.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "skeinrank.selectorLabels" -}}
app.kubernetes.io/name: {{ include "skeinrank.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "skeinrank.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "skeinrank.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "skeinrank.image" -}}
{{- $repo := .repository -}}
{{- $root := .root -}}
{{- printf "%s/%s/%s:%s" $root.Values.image.registry $root.Values.image.namespace $repo $root.Values.image.tag -}}
{{- end -}}

{{- define "skeinrank.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "skeinrank.fullname" .) -}}
{{- end -}}
{{- end -}}
