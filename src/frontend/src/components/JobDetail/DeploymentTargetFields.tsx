import type {
  DeliveryFormat,
  DeploymentComputeMode,
  DeploymentIngestionApproach,
  DeploymentProvider,
  DeploymentTarget,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface DeploymentTargetFieldsProps {
  value: DeploymentTarget;
  onChange: (next: DeploymentTarget) => void;
  schemaPlaceholder?: string;
  disabled?: boolean;
}

interface ToggleOption<T extends string> {
  value: T;
  label: string;
}

const DELIVERY_FORMAT_OPTIONS: ToggleOption<DeliveryFormat>[] = [
  { value: "dlt", label: "DLT pipeline" },
  { value: "spark_job", label: "Classic Spark Job" },
];

const PROVIDER_OPTIONS: ToggleOption<DeploymentProvider>[] = [
  { value: "azure", label: "Azure" },
  { value: "aws", label: "AWS" },
  { value: "gcp", label: "GCP" },
];

const INGESTION_OPTIONS: ToggleOption<DeploymentIngestionApproach>[] = [
  { value: "historical", label: "Historical" },
  { value: "staging", label: "Staging" },
];

const COMPUTE_OPTIONS: ToggleOption<DeploymentComputeMode>[] = [
  { value: "serverless", label: "Serverless" },
  { value: "classic", label: "Classic cluster" },
];

function ToggleRow<T extends string>({
  label,
  description,
  options,
  selected,
  onSelect,
  disabled,
}: {
  label: string;
  description?: string;
  options: ToggleOption<T>[];
  selected: T;
  onSelect: (value: T) => void;
  disabled?: boolean;
}): React.ReactElement {
  return (
    <div className="space-y-1.5">
      <span className="text-sm font-medium leading-none">{label}</span>
      {description ? (
        <p className="text-xs text-muted-foreground leading-snug">
          {description}
        </p>
      ) : null}
      <div className="flex gap-2" role="group" aria-label={label}>
        {options.map((opt) => (
          <Button
            key={opt.value}
            type="button"
            size="sm"
            variant={selected === opt.value ? "default" : "outline"}
            aria-pressed={selected === opt.value}
            onClick={() => onSelect(opt.value)}
            disabled={disabled}
            className="cursor-pointer"
          >
            {opt.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

const INPUT_CLASS = cn(
  "w-full rounded-md border border-input bg-background",
  "px-3 py-2 text-sm placeholder:text-muted-foreground",
  "focus:outline-none focus:ring-1 focus:ring-ring",
);

export default function DeploymentTargetFields({
  value,
  onChange,
  schemaPlaceholder,
  disabled,
}: DeploymentTargetFieldsProps): React.ReactElement {
  return (
    <div className="space-y-4">
      <ToggleRow
        label="Delivery format"
        description="DLT pipeline (Lakeflow Pipelines) or a classic multi-task Spark Job. DLT needs a Lakeflow-enabled workspace."
        options={DELIVERY_FORMAT_OPTIONS}
        selected={value.delivery_format ?? "dlt"}
        onSelect={(delivery_format) => onChange({ ...value, delivery_format })}
        disabled={disabled}
      />
      <ToggleRow
        label="Cloud provider"
        description="Sets the storage URI scheme and workspace auth host in the bundle (abfss:// · s3:// · gs://)."
        options={PROVIDER_OPTIONS}
        selected={value.provider ?? "azure"}
        onSelect={(provider) => onChange({ ...value, provider })}
        disabled={disabled}
      />
      <ToggleRow
        label="Data ingestion"
        description="How source data lands in Databricks. Tailors the deployment guide only — it doesn't change generated code."
        options={INGESTION_OPTIONS}
        selected={value.ingestion_approach ?? "historical"}
        onSelect={(ingestion_approach) =>
          onChange({ ...value, ingestion_approach })
        }
        disabled={disabled}
      />
      <ToggleRow
        label="Compute"
        description="Serverless (recommended), or a classic cluster with placeholder node types you confirm before deploy."
        options={COMPUTE_OPTIONS}
        selected={value.compute_mode ?? "serverless"}
        onSelect={(compute_mode) => onChange({ ...value, compute_mode })}
        disabled={disabled}
      />

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label
            htmlFor="deploy-catalog"
            className="text-sm font-medium leading-none"
          >
            Catalog
          </label>
          <input
            id="deploy-catalog"
            type="text"
            className={INPUT_CLASS}
            placeholder="main"
            value={value.catalog ?? ""}
            onChange={(e) => onChange({ ...value, catalog: e.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor="deploy-schema"
            className="text-sm font-medium leading-none"
          >
            Schema
          </label>
          <input
            id="deploy-schema"
            type="text"
            className={INPUT_CLASS}
            placeholder={schemaPlaceholder ?? "target schema"}
            value={value.schema ?? ""}
            onChange={(e) => onChange({ ...value, schema: e.target.value })}
            disabled={disabled}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        These set defaults in the generated Databricks bundle; you can also
        override them at deploy time.
      </p>
    </div>
  );
}
