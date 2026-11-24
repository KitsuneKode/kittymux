export type ClassValue = string | false | null | undefined | Record<string, unknown> | ((...args: never[]) => unknown)

export const cn = (...inputs: ClassValue[]) =>
  inputs.filter((x): x is string => typeof x === 'string' && x.length > 0).join(' ')
