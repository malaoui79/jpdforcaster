import logging

import numpy as np
import pandas as pd

import jpddsforcasting.toolbox as tb
import jpddsforcasting.modelbox as mb

logger = logging.getLogger(__name__)


class Ewma(object):
    """
    Blabla
    """

    config_schema = ['window_size']

    # default
    ewma_config = None
    window_size = 10
    stationarityModel = None

    def __init__(self, ewma_config, full_history=None):

        self.ewma_config = ewma_config
        self.ewma_config.add_specific_schema(self.config_schema)
        self.ewma_config.m_config_validator()

        self.full_history = full_history
        self.window_size = self.ewma_config.m_config['window_size']
        self.stationarityModel = mb.stationarityModelHandling()

    def fit(self, df):

        self.full_history = tb.validate_time_series_struct(df)

        logger.info("Je suis un fitter exponential weighting moving average")

        self.stationarityModel.fit(df)

        return self

    def predict(self, df):

        logger.info('Do the forecast on the future')

        df['yhat'], variance_coeff = self.__compute_the_future(df)
        df['yhat_upper'] = df['yhat'].apply(lambda x: x + variance_coeff * x)
        df['yhat_lower'] = df['yhat'].apply(lambda x: x - variance_coeff * x)

        return df

    def __compute_the_future(self, df_with_future):
        
        stModel = self.stationarityModel.predict(df_with_future)

        df_with_future = df_with_future.join(self.full_history[['y']], how='outer')

        max_history_date = self.full_history.ds.max()
        histoSize = len(self.full_history.y)
        residual = self.full_history.y - stModel.trend[:histoSize]

        fwd_predictions = pd.Series(residual).ewm(ignore_na=False,span=self.window_size,min_periods=0,adjust=True).mean() # take EWMA in fwd direction
        bwd_predictions = pd.Series(residual[::-1]).ewm(ignore_na=False,span=self.window_size,min_periods=0,adjust=True).mean() # take EWMA in bwd direction
        fwd_predictions = fwd_predictions.fillna(method='bfill')
        bwd_predictions = bwd_predictions.fillna(method='bfill')
        
        filtered = np.vstack(( fwd_predictions, bwd_predictions[::-1])) # lump fwd and bwd together
        predictions = np.mean(filtered, axis=0 ) # average them

        is_to_forcast = (df_with_future.ds > max_history_date)
        iterator = range(len(is_to_forcast))
        temp = residual[-self.window_size:]
        for i in iterator:
            if is_to_forcast[i]:
                yhat_fwd = pd.Series(temp[-self.window_size:]).ewm(ignore_na=False,span=self.window_size,min_periods=0,adjust=True).mean()
                yhat_bwd = pd.Series(temp[-self.window_size:][::-1]).ewm(ignore_na=False,span=self.window_size,min_periods=0,adjust=True).mean()
                
                yhat_fwd = yhat_fwd.fillna(method='bfill')
                yhat_bwd = yhat_bwd.fillna(method='bfill')
                
                yhat = np.mean(np.vstack(( yhat_fwd, yhat_bwd[::-1])),axis=0)[-1:]
                    
                temp = np.append(temp, yhat) # Recursive Multi-step Forecast
                predictions = np.append(predictions, yhat)

        predictions = predictions + stModel.trend + stModel.seasonal       
        var_coef = tb.cv_rmse_evaluation(self.full_history.y,predictions[:histoSize])
        var_coef = var_coef + (stModel.trend_upper-stModel.trend_lower).mean() + (stModel.seasonal_upper-stModel.seasonal_lower).mean()
        return predictions, var_coef
