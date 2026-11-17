import {archivesApi} from '../api/archives.js';
export const archivesStore={items:[],async refresh(){this.items=await archivesApi.list();return this.items;}};
