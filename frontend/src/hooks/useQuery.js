import { useMutation, useQuery } from '@tanstack/react-query';
import api from '../services/api';

// Execute natural language query (Direct)
export const useQueryMutation = () => {
    return useMutation({
        mutationFn: async (data) => {
            const response = await api.post('/query/execute', data);
            return response.data;
        }
    });
};

// Get a query plan
export const usePlanMutation = () => {
    return useMutation({
        mutationFn: async (data) => {
            const response = await api.post('/query/plan', data);
            return response.data;
        }
    });
};

// Execute a confirmed query
export const useExecuteConfirmedMutation = () => {
    return useMutation({
        mutationFn: async (data) => {
            const response = await api.post('/query/execute-confirmed', data);
            return response.data;
        }
    });
};

// Get query history
export const useQueryHistory = (limit = 50, skip = 0) => {
    return useQuery({
        queryKey: ['queryHistory', limit, skip],
        queryFn: async () => {
            const response = await api.get(`/query/history?limit=${limit}&skip=${skip}`);
            return response.data.data;
        }
    });
};

// Get conversation by ID
export const useConversation = (conversationId) => {
    return useQuery({
        queryKey: ['conversation', conversationId],
        queryFn: async () => {
            const response = await api.get(`/query/conversation/${conversationId}`);
            return response.data.data;
        },
        enabled: !!conversationId
    });
};

// Delete query from history
export const useDeleteQuery = () => {
    return useMutation({
        mutationFn: async (queryId) => {
            const response = await api.delete(`/query/history/${queryId}`);
            return response.data;
        }
    });
};
