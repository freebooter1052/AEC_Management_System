/* Password rules - the same as the API (accounts/serializers.validate_password_strength), checked first for quick feedback. */
export const MIN_PASSWORD = 8; // backend AUTH_MIN_PASSWORD_LENGTH

export function passwordProblem(pw) {
  if (!pw) return "Enter a new password.";
  if (pw.length < MIN_PASSWORD) return `Use at least ${MIN_PASSWORD} characters.`;
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Use both letters and numbers.";
  return "";
}

/** Field errors for the change-password form ({current, next, confirm}); empty when it may be sent. */
export function validateChange({ current, next, confirm }) {
  const errors = {};
  if (!current) errors.current_password = "Enter your current password.";
  const problem = passwordProblem(next);
  if (problem) errors.new_password = problem;
  else if (next === current) errors.new_password = "Choose a password different from your current one.";
  if (!confirm) errors.confirm = "Enter the new password again.";
  else if (!errors.new_password && confirm !== next) errors.confirm = "The two passwords do not match.";
  return errors;
}
