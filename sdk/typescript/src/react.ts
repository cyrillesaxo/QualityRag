import {useMemo} from "react";
import {evaluate, type Evidence, type PackSpec, type Evaluation} from "./index.js";

/** Pure local evaluation; React never grants permission to produce an answer. */
export function useQualityRag(pack:PackSpec, evidence:Evidence[], asOf?:string):Evaluation {
  return useMemo(()=>evaluate(pack,evidence,asOf),[pack,evidence,asOf]);
}
