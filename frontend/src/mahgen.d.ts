// mahgen 1.0 exposes runtime exports but omits types from package exports.
declare module 'mahgen' {
  export class Mahgen {
    static render(seq: string, river: boolean): Promise<string>
  }
}
