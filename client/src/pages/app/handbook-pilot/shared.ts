// A prompt handed to the composer from outside the Console (a requirement's
// Draft button). `nonce` makes re-picking the same requirement re-seed.
export type ComposerSeed = { text: string; nonce: number }
