import argparse
from string import ascii_lowercase

import numpy as np
import pandas as pd

from pyspark.sql import SparkSession

from parallelm.mlops import StatCategory as st
from parallelm.mlops import mlops as mlops
from parallelm.mlops.common.spark_pipeline_model_helper import SparkPipelineModelHelper
from parallelm.mlops.predefined_stats import PredefinedStats
from parallelm.mlops.stats.bar_graph import BarGraph

def parse_args():
    """
    Parse Arguments from component
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-model", help="Path of input model to create")
    parser.add_argument("--temp-shared-path", help="Temporary shared path for model transfer")
    options = parser.parse_args()
    return options


def main():
    # Initialize spark and MLOps
    spark = SparkSession.builder.appName("RandomForestClassifier").getOrCreate()
    mlops.init(spark.sparkContext)

    # parse the arguments to component
    options = parse_args()

    # Load the model, exit gracefully if model is not found
    try:
        model_rf = \
            SparkPipelineModelHelper() \
                .set_shared_context(spark_context=spark.sparkContext) \
                .set_local_path(local_path=options.input_model) \
                .set_shared_path_prefix(shared_path_prefix=options.temp_shared_path) \
                .load_sparkml_model()
    except Exception as e:
        print(e)
        mlops.done()
        spark.sparkContext.stop()
        exit()

    # Generate synthetic data for inference (Gaussian Distribution, Poisson Distribution and Beta Distribution)
    num_samples = 50
    num_features = 20

    np.random.seed(0)
    g = np.random.normal(0, 1, (num_samples, num_features))
    p = np.random.poisson(0.7, (num_samples, num_features))
    b = np.random.beta(2, 2, (num_samples, num_features))
    test_data = np.concatenate((g, p, b), axis=0)
    np.random.seed()
    test_features = test_data[np.random.choice(test_data.shape[0], num_samples, replace=False)]
    feature_names = ["".join(ascii_lowercase[a]) for a in range(num_features + 1)]

    # Create a spark dataframe from the synthetic data generated
    inferenceData = spark.createDataFrame(pd.DataFrame(test_features, columns=feature_names[1:num_features + 1]))

    # Output Health Statistics to MCenter
    # MLOps API to report the distribution statistics of each feature in the data and compare it automatically with the ones
    # reported during training to generate the similarity score
    mlops.set_data_distribution_stat(inferenceData)

    num_samples = inferenceData.count()

    # Report the number of samples being processed using MCenter
    mlops.set_stat(PredefinedStats.PREDICTIONS_COUNT, num_samples, st.TIME_SERIES)

    # Make inference predictions
    predicted_df = model_rf.transform(inferenceData)

    # Create a bar graph with label and confidence distributions
    histogram_predictions = predicted_df.groupby("prediction").count()
    prediction_values = np.array(histogram_predictions.select("prediction").collect())
    prediction_counts = np.array(histogram_predictions.select("count").collect())

    # Report label distribution as a BarGraph using MCenter
    bar_predictions = BarGraph().name("Prediction Distribution").cols((prediction_values[0]).astype(str).tolist()).data(
        (prediction_counts[0]).tolist())
    mlops.set_stat(bar_predictions)

    # Stop spark context and MLOps
    spark.sparkContext.stop()
    mlops.done()


if __name__ == "__main__":
    main()
