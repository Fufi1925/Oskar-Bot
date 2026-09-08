import {IdeaDetail} from "@/components/ideas-system";
export const dynamic="force-dynamic";
export default function Page({params}:{params:{ideaId:string}}){return <IdeaDetail id={params.ideaId}/>}
