import {api} from './client.js';
export const archivesApi={list:()=>api('/archives'),create:data=>api('/archives','POST',data),retry:id=>api('/archives/'+id+'/retry','POST')};
