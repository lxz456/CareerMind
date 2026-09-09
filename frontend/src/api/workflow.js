import request from './index'

export const startCareerPlanning = (data) => request.post('/workflow/career-planning', data)
export const getWorkflowStatus = (runId) => request.get(`/workflow/${runId}/status`)
export const resumeCareerPlanning = (runId) => request.post(`/workflow/${runId}/resume`)
export const getWorkflowResult = (runId) => request.get(`/workflow/${runId}/result`)
export const listPlanHistory = () => request.get('/workflow/plans')
export const deletePlan = (runId) => request.delete(`/workflow/plans/${runId}`)
