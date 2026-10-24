export function optionValue(option) {
  return typeof option === "string" ? option : option.value;
}

export function optionLabel(option) {
  return typeof option === "string" ? option : option.label;
}

export function blankProfile(fields) {
  const profile = {};
  for (const field of fields) {
    profile[field.name] = field.name === "country" ? "Ethiopia" : "";
  }
  return profile;
}

export function FieldControl({ field, value, onChange, id }) {
  const common = {
    id,
    name: field.name,
    value: value ?? "",
    onChange: (event) => onChange(field.name, event.target.value),
  };
  if (field.kind === "textarea") {
    return <textarea {...common} rows={3} required={field.required} />;
  }
  if (field.kind === "select") {
    return (
      <select {...common} required={field.required}>
        <option value="">{field.required ? "Choose one" : "Not specified"}</option>
        {(field.options || []).map((option) => (
          <option key={optionValue(option)} value={optionValue(option)}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      {...common}
      type={field.kind === "number" ? "number" : "text"}
      min={field.min}
      max={field.max}
      step={field.step}
      inputMode={field.kind === "number" ? "decimal" : undefined}
      required={field.required}
      autoComplete="off"
    />
  );
}

export function ProfileFields({ fields, profile, onChange, idPrefix = "" }) {
  return (
    <div className="grid">
      {fields.map((field) => {
        if (field.name === "english_score" && !["IELTS", "TOEFL"].includes(profile.english_test)) {
          return null;
        }
        return (
          <label key={field.name} className={field.wide ? "wide" : ""}>
            <span>
              {field.label}
              {field.required ? " *" : ""}
            </span>
            <FieldControl
              field={field}
              value={profile[field.name]}
              onChange={onChange}
              id={`${idPrefix}${field.name}`}
            />
            {field.hint && <small>{field.hint}</small>}
          </label>
        );
      })}
    </div>
  );
}
